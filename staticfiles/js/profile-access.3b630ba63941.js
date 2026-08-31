(function () {
    'use strict';
    // Keep native selects usable if the enhancement cannot load.
    var $ = window.jQuery;
    if (!$ || !$.fn.select2) return;
    ['client', 'sponsor'].forEach(function (name) {
        var field = document.querySelector('.profile-access select[name="' + name + '"]');
        if (!field) return;
        var placeholder = 'Search for a ' + name;
        $(field).select2({
            width: '100%',
            placeholder: placeholder,
            allowClear: true,
            minimumResultsForSearch: 0
        }).on('select2:open', function () {
            var dropdown = document.querySelector('.select2-container--open .select2-dropdown');
            if (dropdown) dropdown.classList.add('profile-access-dropdown');
            var search = document.querySelector('.select2-container--open .select2-search__field');
            if (search) {
                search.placeholder = placeholder;
                search.setAttribute('aria-label', placeholder);
                search.focus();
            }
        });
    });
}());
