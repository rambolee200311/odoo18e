// ========================================
// Marstek Stock Portal - 货位搜索功能
// 功能：搜索并选择货位
// ========================================
(function() {
    'use strict';

    var searchTimeout = null;
    var currentXhr = null;

    function initLocationSearch() {
        var searchInput = document.getElementById('location_search');
        var dropdown = document.getElementById('location_dropdown');
        var hiddenInput = document.getElementById('location_id');

        if (!searchInput || !dropdown || !hiddenInput) return;

        // 监听输入
        searchInput.addEventListener('input', function() {
            var query = this.value.trim();

            // 清空选择
            if (query !== hiddenInput.getAttribute('data-name')) {
                hiddenInput.value = '';
            }

            // 防抖
            clearTimeout(searchTimeout);
            if (query.length === 0) {
                hideDropdown();
                return;
            }

            searchTimeout = setTimeout(function() {
                searchLocations(query);
            }, 300);
        });

        // 点击外部关闭下拉
        document.addEventListener('click', function(e) {
            var wrapper = document.getElementById('location_wrapper');
            if (wrapper && !wrapper.contains(e.target)) {
                hideDropdown();
            }
        });

        // 聚焦时如果已有内容则显示下拉
        searchInput.addEventListener('focus', function() {
            if (this.value.trim().length > 0) {
                searchLocations(this.value.trim());
            }
        });

        // 键盘导航
        searchInput.addEventListener('keydown', function(e) {
            var items = dropdown.querySelectorAll('.dropdown-item:not(.disabled)');
            var activeIndex = -1;

            items.forEach(function(item, index) {
                if (item.classList.contains('active')) {
                    activeIndex = index;
                    item.classList.remove('active');
                }
            });

            if (e.key === 'ArrowDown') {
                e.preventDefault();
                var nextIndex = activeIndex < items.length - 1 ? activeIndex + 1 : 0;
                if (items[nextIndex]) {
                    items[nextIndex].classList.add('active');
                    items[nextIndex].scrollIntoView({ block: 'nearest' });
                }
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                var prevIndex = activeIndex > 0 ? activeIndex - 1 : items.length - 1;
                if (items[prevIndex]) {
                    items[prevIndex].classList.add('active');
                    items[prevIndex].scrollIntoView({ block: 'nearest' });
                }
            } else if (e.key === 'Enter') {
                e.preventDefault();
                if (activeIndex >= 0 && items[activeIndex]) {
                    items[activeIndex].click();
                }
            } else if (e.key === 'Escape') {
                hideDropdown();
            }
        });
    }

    function searchLocations(query) {
        var dropdown = document.getElementById('location_dropdown');
        var loading = document.getElementById('location_loading');
        var searchInput = document.getElementById('location_search');

        // 取消之前的请求
//        if (currentXhr) {
//            currentXhr.abort();
//            currentXhr = null;
//        }

        if (loading) loading.style.display = 'block';

        var url = '/my/marstek/stock/location_options?q=' + encodeURIComponent(query);

//        currentXhr =
        fetch(url)
            .then(function(response) {
                if (!response.ok) throw new Error('Network error');
                return response.json();
            })
            .then(function(data) {
                if (loading) loading.style.display = 'none';
                renderDropdown(data, searchInput.value.trim());
            })
            .catch(function(err) {
                if (loading) loading.style.display = 'none';
                if (err.name !== 'AbortError') {
                    console.error('搜索货位失败:', err);
                    renderDropdown([], query);
                }
            });
    }

    function renderDropdown(locations, query) {
        var dropdown = document.getElementById('location_dropdown');
        var searchInput = document.getElementById('location_search');
        if (!dropdown || !searchInput) return;

        if (locations.length === 0) {
            dropdown.innerHTML = '<div class="dropdown-item-text text-muted">No results found</div>';
            showDropdown();
            return;
        }

        var html = '';
        locations.forEach(function(loc) {
            // 高亮匹配文字
            var displayName = highlightMatch(loc.location_name, query);
            html += '<a class="dropdown-item" href="#" data-id="' + loc.location_id + '" data-name="' + escapeHtml(loc.location_name) + '">';
            html += '<i class="fa fa-map-marker me-2 text-muted"></i>' + displayName;
            html += '</a>';
        });

        dropdown.innerHTML = html;
        showDropdown();

        // 绑定点击事件
        dropdown.querySelectorAll('.dropdown-item[data-id]').forEach(function(item) {
            item.addEventListener('click', function(e) {
                e.preventDefault();
                selectLocation(this);
            });
        });
    }

    function highlightMatch(text, query) {
        if (!query) return escapeHtml(text);
        var escaped = escapeHtml(text);
        var regex = new RegExp('(' + escapeRegex(query) + ')', 'gi');
        return escaped.replace(regex, '<strong class="text-primary">$1</strong>');
    }

    function escapeRegex(string) {
        return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }

    function selectLocation(item) {
        var dropdown = document.getElementById('location_dropdown');
        var searchInput = document.getElementById('location_search');
        var hiddenInput = document.getElementById('location_id');

        var id = item.getAttribute('data-id');
        var name = item.getAttribute('data-name');

        searchInput.value = name;
        searchInput.setAttribute('data-name', name);
        hiddenInput.value = id;
        hiddenInput.setAttribute('data-name', name);

        hideDropdown();
        searchInput.focus();
    }

    function showDropdown() {
        var dropdown = document.getElementById('location_dropdown');
        if (dropdown) dropdown.style.display = 'block';
    }

    function hideDropdown() {
        var dropdown = document.getElementById('location_dropdown');
        if (dropdown) dropdown.style.display = 'none';
    }

    function escapeHtml(text) {
        if (!text) return '';
        var div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // 页面加载完成后初始化
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initLocationSearch);
    } else {
        initLocationSearch();
    }

})();
