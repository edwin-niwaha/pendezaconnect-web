(function () {
  'use strict';

  var input = document.getElementById('report-search');
  var clearButton = document.getElementById('clear-report-search');
  var status = document.getElementById('report-search-status');
  var emptyState = document.getElementById('report-empty-state');
  if (!input || !clearButton || !status || !emptyState) return;

  var cards = Array.prototype.slice.call(document.querySelectorAll('.featured-card, .report-link'));
  var groups = Array.prototype.slice.call(document.querySelectorAll('.report-group'));
  var featured = document.querySelector('.featured-reports');

  function filterReports() {
    var query = input.value.trim().toLocaleLowerCase();
    var visibleCount = 0;

    cards.forEach(function (card) {
      var visible = !query || card.textContent.toLocaleLowerCase().indexOf(query) !== -1;
      card.hidden = !visible;
      if (visible) visibleCount += 1;
    });

    groups.forEach(function (group) {
      group.hidden = !group.querySelector('.report-link:not([hidden])');
    });

    if (featured) featured.hidden = !featured.querySelector('.featured-card:not([hidden])');
    clearButton.hidden = !query;
    emptyState.hidden = visibleCount !== 0;
    status.textContent = query ? visibleCount + (visibleCount === 1 ? ' report found' : ' reports found') : 'All reports';
  }

  input.addEventListener('input', filterReports);
  clearButton.addEventListener('click', function () {
    input.value = '';
    filterReports();
    input.focus();
  });
}());
