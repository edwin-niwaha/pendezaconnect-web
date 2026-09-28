(function () {
    const search = document.getElementById('coaSearch');
    const empty = document.getElementById('coaNoResults');
    if (!search) return;

    search.addEventListener('input', function () {
      const query = this.value.trim().toLowerCase();
      let visibleRows = 0;

      document.querySelectorAll('[data-coa-section]').forEach((section) => {
        let sectionRows = 0;
        section.querySelectorAll('[data-coa-row]').forEach((row) => {
          const show = !query || row.textContent.toLowerCase().includes(query);
          row.classList.toggle('d-none', !show);
          if (show) sectionRows += 1;
        });
        section.classList.toggle('d-none', sectionRows === 0);
        visibleRows += sectionRows;
      });

      if (empty) empty.classList.toggle('d-none', visibleRows > 0);
    });
  })();

