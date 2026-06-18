/**
 * Class-wise Student Filter
 * Call initClassFilter(filterId) for each filter pair on the page.
 * The class filter select must have class="search-select" removed from the
 * global init loop to avoid double-init — this function handles it.
 */
function initClassFilter(filterId) {
    var classFilter = document.getElementById('classFilter_' + filterId);
    var studentSelect = document.getElementById('studentSelect_' + filterId);
    if (!classFilter || !studentSelect) return;

    // Save original options before TomSelect modifies the DOM
    var originalHTML = studentSelect.innerHTML;

    var studentTS = new TomSelect(studentSelect, {
        create: false,
        sortField: null
    });

    // Listen for change on the class filter (works whether TomSelect is on it or not)
    classFilter.addEventListener('change', function () {
        var selected = this.value;

        // Destroy current student TomSelect
        studentTS.destroy();

        // Restore original options
        studentSelect.innerHTML = originalHTML;

        // Remove non-matching optgroups
        if (selected !== 'all') {
            var optgroups = studentSelect.querySelectorAll('optgroup');
            for (var i = 0; i < optgroups.length; i++) {
                if (optgroups[i].label !== selected) {
                    optgroups[i].remove();
                }
            }
        }

        studentTS = new TomSelect(studentSelect, {
            create: false,
            sortField: null
        });
    });
}
