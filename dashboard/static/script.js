document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const emailList = document.getElementById('email-list');
    const emailCount = document.getElementById('email-count');
    const contentViewer = document.getElementById('content-viewer');
    const viewerPlaceholder = document.getElementById('viewer-placeholder');
    const viewerContent = document.getElementById('viewer-content');
    const emailIframe = document.getElementById('email-iframe');
    const metadataPanel = document.getElementById('metadata-panel');
    const searchBar = document.getElementById('search-bar');
    const assetTagsFilter = document.getElementById('asset-tags-filter');
    const banksFilter = document.getElementById('banks-filter');
    const activeFiltersContainer = document.getElementById('active-filters-container');
    const tickerContent = document.getElementById('ticker-content');
    const lastUpdated = document.getElementById('last-updated');
    const resizer = document.getElementById('sidebar-resizer');

    // State 
    let allEmails = [];
    let activeFilters = {
        search: '',
        asset_tags: new Set(),
        banks: new Set(),
        dateFrom: '',
        dateTo: ''
    };

    // I probably should have this shared between this and the python but this is fine for now
    const ASSET_TAXONOMY = {
        "Macro": ["Developed Markets", "Emerging Markets"],
        "Fixed Income": ["Credit Strategy", "Rates Strategy", "Securitisation"],
        "Equity": ["Company Research", "Portfolio Strategy", "Thematic Investing"],
        "Commodities": ["Energy", "Metals", "Agriculture"],
        "FX": ["USD", "EUR", "JPY", "GBP", "CHF", "Other"],
        "Thematics": [],
        "Market Wrap": []
    };

    // Initialization
    async function initializeDashboard() {
        fetchNews();
        const emails = await fetchEmails();
        if (emails) {
            allEmails = emails;
            populateFilterOptions(allEmails);
            renderEmailList();
            addEventListeners();
        }
    }

    // Data Fetching
    async function fetchEmails() {
        try {
            const response = await fetch('/api/emails');
            if (!response.ok) throw new Error('Failed to fetch emails');
            return await response.json();
        } catch (error) {
            console.error(error);
            emailList.innerHTML = '<li>Error loading emails.</li>';
            return null;
        }
    }

    async function fetchNews() {
        try {
            const response = await fetch('/api/news');
            if (!response.ok) throw new Error('Failed to fetch news');
            const data = await response.json();
            renderNewsTicker(data);
        } catch (error) {
            console.error(error);
            tickerContent.innerHTML = '<div class="ticker-item">Could not load news.</div>';
        }
    }

    // UI Rendering
    function renderNewsTicker(data) {
        const updatedTime = new Date(data.last_updated).toLocaleTimeString();
        lastUpdated.textContent = `(Updated: ${updatedTime})`;

        const headlinesHtml = data.headlines.map(item => `
            <div class="ticker-item">
                <a href="${item.link}" target="_blank" rel="noopener noreferrer">${item.headline}</a>
            </div>
        `).join('');
        // Duplicate content for seamless scrolling
        tickerContent.innerHTML = headlinesHtml + headlinesHtml;
    }

    function renderEmailList() {
        let filteredEmails = [...allEmails];

        // Apply search filter
        if (activeFilters.search) {
            const searchTerm = activeFilters.search.toLowerCase();
            filteredEmails = filteredEmails.filter(email =>
                (email.folder_name && email.folder_name.toLowerCase().includes(searchTerm)) ||
                (email.bank && email.bank.toLowerCase().includes(searchTerm)) ||
                (email.companies_mentioned && email.companies_mentioned.some(c => c.toLowerCase().includes(searchTerm)))
            );
        }

        // Apply date filter
        if (activeFilters.dateFrom || activeFilters.dateTo) {
            filteredEmails = filteredEmails.filter(email => {
                if (!email.date || email.date === "Unknown") return false;
                const d = email.date.trim();
                if (activeFilters.dateFrom && d < activeFilters.dateFrom) return false;
                if (activeFilters.dateTo && d > activeFilters.dateTo) return false;
                return true;
            });
        }

        // Apply bank filter
        if (activeFilters.banks.size > 0) {
            filteredEmails = filteredEmails.filter(email => email.bank && activeFilters.banks.has(email.bank));
        }

        // Apply asset tag filter
        if (activeFilters.asset_tags.size > 0) {
            filteredEmails = filteredEmails.filter(email =>
                email.asset_tags && email.asset_tags.some(tag => activeFilters.asset_tags.has(tag))
            );
        }

        emailCount.textContent = filteredEmails.length;
        emailList.innerHTML = filteredEmails.map((email, index) => `
            <li class="email-item" data-id="${email.source_file}">
                <h4>${email.folder_name || 'No Title'}</h4>
                <div class="meta">
                    <span>${email.bank || 'Unknown Bank'}</span> | <span>${email.date || 'Unknown Date'}</span>
                </div>
                <div class="tags">
                    ${(email.asset_tags || []).map(tag => `<span class="tag">${tag}</span>`).join('')}
                </div>
            </li>
        `).join('');

        // Add click listeners to new list items
        emailList.querySelectorAll('.email-item').forEach(item => {
            item.addEventListener('click', () => handleEmailSelection(item));
        });
    }

    function displayEmailContent(email) {
        viewerPlaceholder.classList.add('hidden');
        viewerContent.classList.remove('hidden');

        // Set iframe source to fetch HTML content
        emailIframe.src = `/api/email/${email.source_file}`;

        // Populate metadata panel
        const companies = email.companies_mentioned || [];
        const industries = email.industry_subindustry || [];
        const pdfs = email.pdf_attachment || [];

        metadataPanel.innerHTML = `
            <div class="meta-group">
                <h5>Companies</h5>
                <ul>${companies.length > 0 ? companies.map(c => `<li>${c}</li>`).join('') : '<li>N/A</li>'}</ul>
            </div>
            <div class="meta-group">
                <h5>Industries</h5>
                <ul>${industries.length > 0 ? industries.map(i => `<li>${i}</li>`).join('') : '<li>N/A</li>'}</ul>
            </div>
            <div class="meta-group">
                <h5>Attachments</h5>
                <ul>${pdfs.length > 0 ? pdfs.map(p => `<li><a href="/api/pdf/${email.source_file}/${p}" target="_blank">${p}</a></li>`).join('') : '<li>N/A</li>'}</ul>
            </div>
        `;
    }

    function populateFilterOptions(emails) {
        const banks = new Set();
        emails.forEach(email => {
            if (email.bank && email.bank !== "Unknown") banks.add(email.bank);
        });

        banksFilter.innerHTML = [...banks].sort().map(bank => `
            <label><input type="checkbox" data-filter="banks" value="${bank}"> ${bank}</label>
        `).join('');

        assetTagsFilter.innerHTML = Object.entries(ASSET_TAXONOMY).map(([parent, subs]) => `
            <div class="asset-category">
                <div class="category-header">
                    <button class="toggle-subs" style="${subs.length === 0 ? 'visibility:hidden' : ''}">▶</button>
                    <label><input type="checkbox" data-filter="asset_tags" value="${parent}"> ${parent}</label>
                </div>
                ${subs.length > 0 ? `
                <div class="sub-tags hidden">
                    ${subs.map(sub => `
                        <label><input type="checkbox" data-filter="asset_tags" value="${sub}"> ${sub}</label>
                    `).join('')}
                </div>` : ''}
            </div>
        `).join('');
    }

    function renderActiveFilterChips() {
        activeFiltersContainer.innerHTML = '';
        for (const [type, values] of Object.entries(activeFilters)) {
            if (type === 'search' && values) {
            } else if (values instanceof Set) {
                values.forEach(value => {
                    const chip = document.createElement('div');
                    chip.className = 'filter-chip';
                    chip.innerHTML = `${value} <button data-type="${type}" data-value="${value}">&times;</button>`;
                    activeFiltersContainer.appendChild(chip);
                });
            }
        }
    }

    // Event Handlers and Listeners
    function addEventListeners() {
        searchBar.addEventListener('input', (e) => {
            activeFilters.search = e.target.value;
            renderEmailList();
        });

        document.getElementById('date-from').addEventListener('change', (e) => {
            activeFilters.dateFrom = e.target.value;
            renderEmailList();
        });

        document.getElementById('date-to').addEventListener('change', (e) => {
            activeFilters.dateTo = e.target.value;
            renderEmailList();
        });

        document.querySelector('.filters-section').addEventListener('change', (e) => {
            if (e.target.type === 'checkbox') {
                const { filter } = e.target.dataset;
                const value = e.target.value;
                if (e.target.checked) {
                    activeFilters[filter].add(value);
                } else {
                    activeFilters[filter].delete(value);
                }
                renderActiveFilterChips();
                renderEmailList();
            }
        });

        document.querySelector('.filters-section').addEventListener('click', (e) => {
            if (e.target.classList.contains('toggle-subs')) {
                const category = e.target.closest('.asset-category');
                const subs = category.querySelector('.sub-tags');
                if (subs) {
                    subs.classList.toggle('hidden');
                    e.target.textContent = subs.classList.contains('hidden') ? '▶' : '▼';
                }
            }
        });

        // Resizer
        if (resizer) {
            resizer.addEventListener('mousedown', (e) => {
                e.preventDefault();
                resizer.classList.add('dragging');
                document.addEventListener('mousemove', handleResizerMove);
                document.addEventListener('mouseup', stopResizerMove);
            });
        }

        function handleResizerMove(e) {
            const filtersSection = document.getElementById('filters-section');
            const sidebar = document.querySelector('.sidebar');
            const sidebarRect = sidebar.getBoundingClientRect();
            const newHeight = e.clientY - sidebarRect.top;

            if (newHeight > 150 && newHeight < sidebarRect.height - 150) {
                filtersSection.style.height = `${newHeight}px`;
            }
        }

        function stopResizerMove() {
            resizer.classList.remove('dragging');
            document.removeEventListener('mousemove', handleResizerMove);
            document.removeEventListener('mouseup', stopResizerMove);
        }

        activeFiltersContainer.addEventListener('click', (e) => {
            if (e.target.tagName === 'BUTTON') {
                const { type, value } = e.target.dataset;
                activeFilters[type].delete(value);
                // Uncheck the corresponding checkbox
                document.querySelector(`input[data-filter="${type}"][value="${value}"]`).checked = false;
                renderActiveFilterChips();
                renderEmailList();
            }
        });
    }

    function handleEmailSelection(selectedItem) {
        // Remove active class from all items
        emailList.querySelectorAll('.email-item').forEach(item => item.classList.remove('active'));
        // Add active class to the selected one
        selectedItem.classList.add('active');

        const emailId = selectedItem.dataset.id;
        const email = allEmails.find(e => e.source_file === emailId);
        if (email) {
            displayEmailContent(email);
        }
    }

    // --- Start the application ---
    initializeDashboard();
});