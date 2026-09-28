(() => {
  const dialog = document.getElementById('client-preview');
  const content = document.getElementById('client-preview-content');
  if (!dialog || !content) return;
  let trigger;
  document.querySelectorAll('[data-client-preview]').forEach(button => {
    button.addEventListener('click', () => {
      const template = document.getElementById(button.dataset.clientPreview);
      if (!template) return;
      trigger = button;
      content.replaceChildren(template.content.cloneNode(true));
      dialog.showModal();
      document.body.classList.add('preview-open');
      content.scrollTop = 0;
      dialog.querySelector('[data-close-preview]').focus();
    });
  });
  dialog.querySelector('[data-close-preview]').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
  dialog.addEventListener('close', () => {
    document.body.classList.remove('preview-open');
    content.replaceChildren();
    if (trigger) trigger.focus();
  });
})();
