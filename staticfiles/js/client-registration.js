(() => {
  const form = document.getElementById('client-registration');
  if (!form) return;
  const steps = Array.from(form.querySelectorAll('.registration-step'));
  const tabs = Array.from(form.querySelectorAll('[data-step-target]'));
  const back = document.getElementById('step-back');
  const next = document.getElementById('step-next');
  const submit = document.getElementById('step-submit');
  const status = document.getElementById('step-status');
  const progress = document.getElementById('step-progress');
  let current = 0;
  let revision = form.dataset.draftRevision;
  let queue = Promise.resolve(true);
  let timer;
  let dirty = false;
  let generation = 0;
  let submitting = false;
  let readyToSubmit = false;
  const savedStatus = document.getElementById('draft-status');
  function changed() {
    if (submitting) return;
    dirty = true;
    generation++;
    savedStatus.textContent = 'Unsaved changes…';
    clearTimeout(timer);
    timer = setTimeout(() => saveDraft(current), 800);
  }
  function saveDraft(step) {
    clearTimeout(timer);
    const version = generation;
    const payload = new FormData(form);
    payload.set('step', String(step));
    payload.set('draft_id', form.dataset.draftId);
    dirty = true;
    queue = queue.then(async () => {
      savedStatus.textContent = 'Saving draft…';
      payload.set('revision', revision);
      try {
        const response = await fetch(form.dataset.draftUrl, {
          method: 'POST', body: payload, credentials: 'same-origin',
          headers: {'X-CSRFToken': payload.get('csrfmiddlewaretoken')},
        });
        if (response.redirected) throw new Error('Your session expired. Sign in again to continue saving.');
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || 'Could not save your draft. Please retry.');
        revision = String(result.revision);
        if (version === generation) {
          dirty = false;
          savedStatus.textContent = 'Draft saved';
        }
        return true;
      } catch (error) {
        dirty = true;
        savedStatus.textContent = error.message || 'Draft not saved. Check your connection and retry.';
        return false;
      }
    });
    return queue;
  }
  form.addEventListener('input', changed);
  form.addEventListener('change', changed);
  window.addEventListener('beforeunload', event => {
    if (dirty && !readyToSubmit) { event.preventDefault(); event.returnValue = ''; }
  });
  form.noValidate = true;
  form.querySelector('[data-wizard-controls]').hidden = false;
  const fields = step => Array.from(step.querySelectorAll('input, select, textarea'));
  function show(index, focus = true) {
    current = index;
    steps.forEach((step, i) => { step.hidden = i !== index; });
    tabs.forEach((tab, i) => {
      if (i === index) tab.setAttribute('aria-current', 'step');
      else tab.removeAttribute('aria-current');
    });
    status.textContent = `Step ${index + 1} of ${steps.length} · ${steps[index].dataset.stepTitle}`;
    progress.max = steps.length;
    progress.value = index + 1;
    back.hidden = index === 0;
    next.hidden = index === steps.length - 1;
    submit.hidden = index !== steps.length - 1;
    if (focus) steps[index].querySelector('h2').focus();
  }
  function validate(index) {
    const invalid = fields(steps[index]).find(field => !field.checkValidity());
    if (!invalid) return true;
    show(index, false);
    invalid.focus();
    invalid.reportValidity();
    return false;
  }
  async function move(target) {
    if (submitting) return;
    if (target > current) {
      for (let i = current; i < target; i++) if (!validate(i)) return;
    }
    if (await saveDraft(target)) show(target);
  }
  back.addEventListener('click', () => move(current - 1));
  next.addEventListener('click', () => move(current + 1));
  tabs.forEach(tab => tab.addEventListener('click', () => move(Number(tab.dataset.stepTarget))));
  form.addEventListener('submit', async event => {
    if (readyToSubmit) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    if (submitting) return;
    if (current < steps.length - 1) { move(current + 1); return; }
    for (let i = 0; i < steps.length; i++) if (!validate(i)) return;
    submitting = true;
    submit.disabled = true;
    if (await saveDraft(current)) {
      readyToSubmit = true;
      submit.disabled = false;
      form.requestSubmit(submit);
    } else {
      submitting = false;
      submit.disabled = false;
    }
  }, true);
  const firstError = steps.findIndex(step => step.querySelector('.is-invalid, .invalid-feedback, .errorlist'));
  show(firstError >= 0 ? firstError : Math.max(0, Math.min(6, Number(form.dataset.draftStep) || 0)), firstError >= 0);
})();
