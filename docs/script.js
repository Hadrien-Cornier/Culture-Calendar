// Global variables
let eventsData = [];
let filteredEvents = [];
let selectedGenres = new Set();
let selectedVenues = new Set();
let showSpecialEventsOnly = false;
let hideWorkHours = false;
let currentMonth = new Date().getMonth();
let currentYear = new Date().getFullYear();
let dateRangeStart = null;
let dateRangeEnd = null;
let currentSort = 'chronological';
let currentView = 'today'; // today, weekend, week, all, calendar

// DOM elements
const ratingSlider = document.getElementById('rating-slider');
const ratingValue = document.getElementById('rating-value');
const downloadBtn = document.getElementById('download-btn');
const eventsList = document.getElementById('events-list');
const eventsHeading = document.getElementById('events-heading');
const eventCountElement = document.getElementById('event-count');
const loadingElement = document.getElementById('loading');
const listView = document.getElementById('list-view');
const calendarView = document.getElementById('calendar-view');
const calendarContainer = document.getElementById('calendar-container');
const specialEventsToggle = document.getElementById('special-events-toggle');
const hideWorkHoursToggle = document.getElementById('hide-work-hours-toggle');
const prevMonthBtn = document.getElementById('prev-month');
const nextMonthBtn = document.getElementById('next-month');
const monthYearDisplay = document.getElementById('month-year-display');
const startDateInput = document.getElementById('start-date');
const endDateInput = document.getElementById('end-date');
const applyDateFilterBtn = document.getElementById('apply-date-filter');
const clearDateFilterBtn = document.getElementById('clear-date-filter');
const updateList = document.getElementById('update-list');
const searchInput = document.getElementById('search-input');
const codeUpdatedElement = document.getElementById('code-updated');
const filterSidebar = document.getElementById('filter-sidebar');
const showFiltersLink = document.getElementById('show-filters-link');
const downloadLink = document.getElementById('download-link');
const closeFiltersBtn = document.getElementById('close-filters');
const navLinks = document.querySelectorAll('.nav-link');
const mastheadDate = document.getElementById('masthead-date');

let searchTerm = '';
let selectedDirector = null;

// Initialize the app
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM Content Loaded'); // Debug log
    
    // Verify critical elements exist
    const criticalElements = ['loading', 'events-list', 'rating-slider'];
    const missingElements = criticalElements.filter(id => !document.getElementById(id));
    
    if (missingElements.length > 0) {
        console.error('Missing critical elements:', missingElements);
        alert('Page not loaded properly. Missing elements: ' + missingElements.join(', '));
        return;
    }
    
    console.log('All critical elements found, proceeding...'); // Debug log
    
    // Unified compact layout is now the default and only mode
    
    updateMastheadDate();
    setupEventListeners();
    loadEventsData();
    loadUpdateInfo();
    loadCodeUpdateTime();
});

// Update masthead date to match wireframe format
function updateMastheadDate() {
    if (mastheadDate) {
        const today = new Date();
        const options = { year: 'numeric', month: 'long', day: 'numeric' };
        const formattedDate = today.toLocaleDateString('en-US', options);
        mastheadDate.textContent = `Culture Calendar · ${formattedDate} · Austin, TX`;
    }
}

// Update event count
function updateEventCount() {
    if (eventCountElement) {
        const count = filteredEvents.length;
        eventCountElement.textContent = `${count} event${count !== 1 ? 's' : ''}`;
    }
}

// Calculate event counts for navigation tabs
function updateNavigationCounts() {
    if (!eventsData || eventsData.length === 0) return;
    
    // Helper function to count events with current filters
    function countEventsForDateRange(startDate, endDate) {
        return eventsData.filter(event => {
            // Apply all current filters
            const minRating = parseInt(ratingSlider.value);
            if (event.rating < minRating) return false;
            
            if (selectedGenres.size > 0 && !selectedGenres.has(event.country)) return false;
            if (selectedVenues.size > 0 && !selectedVenues.has(event.venue)) return false;
            if (showSpecialEventsOnly && !event.isSpecialScreening) return false;
            if (hideWorkHours && event.isWorkHours) return false;
            if (selectedDirector && event.director !== selectedDirector) return false;
            
            if (searchTerm) {
                const fields = [event.title, event.director, event.oneLinerSummary, event.description];
                const haystack = fields.filter(Boolean).join(' ').toLowerCase();
                if (!haystack.includes(searchTerm)) return false;
            }
            
            // Check date range
            if (!event.screenings || !Array.isArray(event.screenings)) return false;
            return event.screenings.some(screening => {
                const screeningDate = parseLocalDate(screening.date);
                screeningDate.setHours(0, 0, 0, 0);
                startDate.setHours(0, 0, 0, 0);
                endDate.setHours(0, 0, 0, 0);
                return screeningDate >= startDate && screeningDate < endDate;
            });
        }).length;
    }
    
    // Calculate counts for each view
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);
    
    // Weekend calculation
    const friday = new Date(today);
    const day = friday.getDay();
    let diffToFriday = day === 0 ? -2 : 5 - day;
    friday.setDate(friday.getDate() + diffToFriday);
    const sunday = new Date(friday);
    sunday.setDate(friday.getDate() + 3); // Through end of Sunday
    
    // Week calculation
    const nextWeek = new Date(today);
    nextWeek.setDate(nextWeek.getDate() + 7);
    
    // Get counts
    const todayCount = countEventsForDateRange(today, tomorrow);
    const weekendCount = countEventsForDateRange(friday, sunday);
    const weekCount = countEventsForDateRange(today, nextWeek);
    const allCount = eventsData.filter(event => {
        const minRating = parseInt(ratingSlider.value);
        if (event.rating < minRating) return false;
        if (selectedGenres.size > 0 && !selectedGenres.has(event.country)) return false;
        if (selectedVenues.size > 0 && !selectedVenues.has(event.venue)) return false;
        if (showSpecialEventsOnly && !event.isSpecialScreening) return false;
        if (hideWorkHours && event.isWorkHours) return false;
        if (selectedDirector && event.director !== selectedDirector) return false;
        if (searchTerm) {
            const fields = [event.title, event.director, event.oneLinerSummary, event.description];
            const haystack = fields.filter(Boolean).join(' ').toLowerCase();
            if (!haystack.includes(searchTerm)) return false;
        }
        return true;
    }).length;
    
    // Update nav links with counts - only show count for active tab
    navLinks.forEach(link => {
        const view = link.dataset.view;
        if (!view) return;
        
        let count = 0;
        switch(view) {
            case 'today': count = todayCount; break;
            case 'weekend': count = weekendCount; break;
            case 'week': count = weekCount; break;
            case 'all': count = allCount; break;
            case 'calendar': count = allCount; break; // Calendar shows all events
        }
        
        // Update link text with count for all tabs
        const baseText = link.textContent.replace(/\s*\(\d+\)/, ''); // Remove existing count
        link.textContent = `${baseText} (${count})`;
    });
}

// Set up event listeners
function setupEventListeners() {
    ratingSlider.addEventListener('input', function() {
        ratingValue.textContent = this.value;
        updateFilteredEvents();
        renderEvents();
        updateNavigationCounts();
        
        // Re-render calendar if it's currently visible
        if (currentView === 'calendar') {
            renderCalendar();
        }
    });

    downloadBtn.addEventListener('click', function() {
        const minRating = parseInt(ratingSlider.value);
        downloadFilteredCalendar(minRating);
    });

    // Navigation links
    navLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            const newView = this.dataset.view;
            if (newView) {
                switchView(newView);
                // Update active state
                navLinks.forEach(l => l.classList.remove('active'));
                this.classList.add('active');
            }
        });
    });

    // Show/hide filters
    if (showFiltersLink) {
        showFiltersLink.addEventListener('click', function(e) {
            e.preventDefault();
            toggleFilterSidebar();
        });
    }
    
    if (closeFiltersBtn) {
        closeFiltersBtn.addEventListener('click', function() {
            toggleFilterSidebar();
        });
    }
    
    // Download link
    if (downloadLink) {
        downloadLink.addEventListener('click', function(e) {
            e.preventDefault();
            const minRating = parseInt(ratingSlider.value);
            downloadFilteredCalendar(minRating);
        });
    }

    if (specialEventsToggle) {
        specialEventsToggle.addEventListener('change', function() {
            showSpecialEventsOnly = this.checked;
            updateFilteredEvents();
            renderEvents();
            updateNavigationCounts();
            if (currentView === 'calendar') {
                renderCalendar();
            }
        });
    }

    if (hideWorkHoursToggle) {
        hideWorkHoursToggle.addEventListener('change', function() {
            hideWorkHours = this.checked;
            updateFilteredEvents();
            renderEvents();
            updateNavigationCounts();
            if (currentView === 'calendar') {
                renderCalendar();
            }
        });
    }

    // Compact mode toggle removed - unified layout only

    prevMonthBtn.addEventListener('click', function() {
        navigateMonth(-1);
    });

    nextMonthBtn.addEventListener('click', function() {
        navigateMonth(1);
    });

    applyDateFilterBtn.addEventListener('click', function() {
        applyDateRangeFilter();
    });

    clearDateFilterBtn.addEventListener('click', function() {
        clearDateRangeFilter();
    });

    if (searchInput) {
        searchInput.addEventListener('input', function() {
            searchTerm = this.value.toLowerCase();
            updateFilteredEvents();
            renderEvents();
            updateNavigationCounts();
            if (currentView === 'calendar') {
                renderCalendar();
            }
        });
    }

    // Click outside to close filter sidebar
    document.addEventListener('click', function(e) {
        if (filterSidebar && filterSidebar.classList.contains('active')) {
            if (!filterSidebar.contains(e.target) && 
                !showFiltersLink.contains(e.target) &&
                !e.target.classList.contains('sidebar-backdrop')) {
                toggleFilterSidebar();
            }
        }
    });
}


// Switch view
function switchView(view) {
    currentView = view;
    
    // Add data attribute to body for current view
    document.body.setAttribute('data-view', view);
    
    switch (view) {
        case 'today':
            filterToday();
            break;
        case 'weekend':
            filterThisWeekend();
            break;
        case 'week':
            filterThisWeek();
            break;
        case 'all':
            clearDateRangeFilter();
            updateFilteredEvents();
            renderEvents();
            eventsHeading.textContent = 'All Upcoming Events';
            switchToListView();
            break;
        case 'calendar':
            clearDateRangeFilter();
            switchToCalendarView();
            break;
    }
}

function filterToday() {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);
    tomorrow.setHours(0, 0, 0, 0);
    
    dateRangeStart = today;
    dateRangeEnd = tomorrow;
    
    updateFilteredEvents();
    renderEvents();
    
    // Update section header
    eventsHeading.textContent = "Today's Events";
    updateEventCount();
    
    // Switch to list view for better readability
    switchToListView();
}

function filterThisWeek() {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const nextWeek = new Date(today);
    nextWeek.setDate(nextWeek.getDate() + 7);
    
    dateRangeStart = today;
    dateRangeEnd = nextWeek;
    
    updateFilteredEvents();
    renderEvents();
    
    // Update section header
    eventsHeading.textContent = "This Week's Events";
    updateEventCount();
    
    // Switch to list view for better readability
    switchToListView();
}

function filterThisWeekend() {
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    // Determine Friday of the current week
    const friday = new Date(today);
    const day = friday.getDay();
    
    // Calculate days to next Friday
    // If it's Monday (1) through Sunday (0), we want this week's Friday
    // getDay() returns: 0=Sunday, 1=Monday, 2=Tuesday, 3=Wednesday, 4=Thursday, 5=Friday, 6=Saturday
    let diffToFriday;
    if (day == 0) {// Sunday
        diffToFriday = -2;
    } else {// Monday (1) through Saturday (6)
        diffToFriday = 5 - day;
    }
 
    friday.setDate(friday.getDate() + diffToFriday);

    const sunday = new Date(friday);
    sunday.setDate(friday.getDate() + 2);
    sunday.setHours(23, 59, 59, 999);

    dateRangeStart = friday;
    dateRangeEnd = sunday;

    updateFilteredEvents();
    renderEvents();

    eventsHeading.textContent = "This Weekend's Events";
    updateEventCount();

    switchToListView();
}

// Toggle filter sidebar
function toggleFilterSidebar() {
    if (filterSidebar) {
        filterSidebar.classList.toggle('active');
        // Add backdrop for mobile
        if (filterSidebar.classList.contains('active')) {
            const backdrop = document.createElement('div');
            backdrop.className = 'sidebar-backdrop';
            backdrop.addEventListener('click', toggleFilterSidebar);
            document.body.appendChild(backdrop);
        } else {
            const backdrop = document.querySelector('.sidebar-backdrop');
            if (backdrop) backdrop.remove();
        }
    }
}

// Switch to list view
function switchToListView() {
    listView.style.display = 'block';
    calendarView.style.display = 'none';
}

// Switch to calendar view
function switchToCalendarView() {
    console.log('Switching to calendar view...'); // Debug log
    
    try {
        listView.style.display = 'none';
        calendarView.style.display = 'block';
        
        console.log('Events data length:', eventsData.length); // Debug log
        
        if (eventsData && eventsData.length > 0) {
            renderCalendar();
        } else {
            console.log('No event data available for calendar');
            calendarContainer.innerHTML = '<div class="loading">Loading calendar data...</div>';
        }
    } catch (error) {
        console.error('Error switching to calendar view:', error);
        calendarContainer.innerHTML = '<div class="loading">Error loading calendar</div>';
    }
}

// Load movies data from JSON file
async function loadEventsData() {
    try {
        console.log('Starting data load process...'); // Debug log
        console.log('Current URL:', window.location.href); // Debug log
        
        // Try absolute URL first, then relative
        let dataUrl = 'data.json';
        if (window.location.hostname === 'hadrien-cornier.github.io') {
            dataUrl = '/Culture-Calendar/data.json';
        }
        
        console.log('Attempting to load:', dataUrl); // Debug log
        const response = await fetch(dataUrl);
        console.log('Fetch response status:', response.status, response.statusText); // Debug log
        console.log('Response headers:', response.headers); // Debug log
        
        if (!response.ok) {
            // Try fallback URL
            if (dataUrl !== 'data.json') {
                console.log('Trying fallback URL: data.json');
                const fallbackResponse = await fetch('data.json');
                if (!fallbackResponse.ok) {
                    throw new Error(`HTTP error! status: ${response.status} - ${response.statusText}`);
                }
                const fallbackData = await fallbackResponse.json();
                eventsData = fallbackData;
            } else {
                throw new Error(`HTTP error! status: ${response.status} - ${response.statusText}`);
            }
        } else {
            eventsData = await response.json();
        }
        
        console.log('Loaded events data:', eventsData?.length, 'events'); // Debug log
        
        // Validate data structure
        if (!Array.isArray(eventsData)) {
            console.error('Invalid data type:', typeof eventsData);
            throw new Error('Invalid data format: expected array, got ' + typeof eventsData);
        }
        
        // Check if we have valid event data
        if (eventsData.length === 0) {
            console.warn('No event data found');
            showError('No cultural events available at this time.');
            return;
        }
        
        console.log('Setting up filters...'); // Debug log
        setupGenreFilters();
        setupVenueFilters();
        // Start with Today's Events view (this will call updateFilteredEvents and renderEvents)
        switchView('today');
        
        // Update navigation counts after data loads
        updateNavigationCounts();
        
        // Check for outdated classical music data
        checkClassicalDataFreshness();
        
        hideLoading();
        
        console.log('Events data loaded successfully'); // Debug log
    } catch (error) {
        console.error('Detailed error loading movies data:', error);
        console.error('Error stack:', error.stack);
        showError(`Failed to load cultural event data: ${error.message}. Please check browser console for details.`);
    }
}

// Load per-source update times
async function loadUpdateInfo() {
    if (!updateList) return;
    try {
        let url = 'source_update_times.json';
        if (window.location.hostname === 'hadrien-cornier.github.io') {
            url = '/Culture-Calendar/source_update_times.json';
        }
        const response = await fetch(url);
        if (!response.ok) return;
        const data = await response.json();
        updateList.innerHTML = '';
        Object.entries(data).forEach(([venue, timestamp]) => {
            const li = document.createElement('li');
            if (timestamp) {
                const date = new Date(timestamp);
                li.textContent = `${getVenueName(venue)} - ${date.toLocaleString()}`;
            } else {
                li.textContent = `${getVenueName(venue)} - n/a`;
            }
            updateList.appendChild(li);
        });
    } catch (err) {
        console.error('Error loading update info', err);
    }
}

// Load timestamp of the latest repository commit
async function loadCodeUpdateTime() {
    if (!codeUpdatedElement) return;
    try {
        const url = 'https://api.github.com/repos/hadrien-cornier/Culture-Calendar/commits?per_page=1';
        const response = await fetch(url);
        if (!response.ok) return;
        const data = await response.json();
        if (Array.isArray(data) && data.length > 0) {
            const commitDate = data[0].commit.committer.date;
            const localDate = new Date(commitDate).toLocaleString();
            codeUpdatedElement.textContent = `Data last updated: ${localDate}`;
        }
    } catch (err) {
        console.error('Error loading code update time', err);
    }
}

// Setup country filter buttons
function setupGenreFilters() {
    const countries = [...new Set(eventsData
        .map(event => event.country)
        .filter(country => country)
    )].sort();
    
    const genreButtonsContainer = document.getElementById('genre-buttons');
    
    // Add "All" button
    const allButton = document.createElement('button');
    allButton.className = 'genre-filter-btn active';
    allButton.textContent = 'All Countries';
    allButton.onclick = () => toggleGenreFilter('all');
    genreButtonsContainer.appendChild(allButton);
    
    // Add country-specific buttons
    countries.forEach(country => {
        const button = document.createElement('button');
        button.className = 'genre-filter-btn';
        button.textContent = country;
        button.onclick = () => toggleGenreFilter(country);
        genreButtonsContainer.appendChild(button);
    });
}

// Setup venue filter buttons
function setupVenueFilters() {
    const venues = [...new Set(eventsData
        .map(event => event.venue)
        .filter(venue => venue)
    )].sort();
    
    console.log('Found venues:', venues); // Debug log
    
    const venueButtonsContainer = document.getElementById('venue-buttons');
    
    // Clear existing buttons
    venueButtonsContainer.innerHTML = '';
    
    // Add "All" button
    const allButton = document.createElement('button');
    allButton.className = 'venue-filter-btn active';
    allButton.textContent = 'All Venues';
    allButton.onclick = () => toggleVenueFilter('all');
    venueButtonsContainer.appendChild(allButton);
    
    // Add venue-specific buttons
    venues.forEach(venue => {
        const button = document.createElement('button');
        button.className = 'venue-filter-btn';
        button.textContent = getVenueName(venue);
        button.onclick = () => toggleVenueFilter(venue);
        venueButtonsContainer.appendChild(button);
        console.log('Added venue button:', venue, getVenueName(venue)); // Debug log
    });
}

// Toggle special events filter
function toggleSpecialEventsFilter() {
    showSpecialEventsOnly = !showSpecialEventsOnly;
    
    if (showSpecialEventsOnly) {
        specialEventsToggle.classList.add('active');
        specialEventsToggle.textContent = 'Show All Events';
    } else {
        specialEventsToggle.classList.remove('active');
        specialEventsToggle.textContent = 'Show Special Events Only';
    }
    
    updateFilteredEvents();
    renderEvents();
    updateNavigationCounts();
    
    // Re-render calendar if it's currently visible
    if (calendarView.style.display !== 'none') {
        renderCalendar();
    }
}

function toggleWorkHoursFilter() {
    hideWorkHours = !hideWorkHours;
    
    if (hideWorkHours) {
        hideWorkHoursToggle.classList.add('active');
        hideWorkHoursToggle.textContent = 'Show Work Hours';
    } else {
        hideWorkHoursToggle.classList.remove('active');
        hideWorkHoursToggle.textContent = 'Hide Work Hours (9am-6pm)';
    }
    
    updateFilteredEvents();
    renderEvents();
    updateNavigationCounts();
    
    // Re-render calendar if it's currently visible
    if (calendarView.style.display !== 'none') {
        renderCalendar();
    }
}

// Toggle genre filter
function toggleGenreFilter(genre) {
    if (genre === 'all') {
        selectedGenres.clear();
        document.querySelectorAll('.genre-filter-btn').forEach(btn => {
            btn.classList.remove('active');
        });
        document.querySelector('.genre-filter-btn').classList.add('active'); // "All" button
    } else {
        // Remove "All" selection
        document.querySelector('.genre-filter-btn').classList.remove('active');
        
        const button = [...document.querySelectorAll('.genre-filter-btn')]
            .find(btn => btn.textContent === genre);
        
        if (selectedGenres.has(genre)) {
            selectedGenres.delete(genre);
            button.classList.remove('active');
        } else {
            selectedGenres.add(genre);
            button.classList.add('active');
        }
        
        // If no genres selected, activate "All"
        if (selectedGenres.size === 0) {
            document.querySelector('.genre-filter-btn').classList.add('active');
        }
    }
    
    updateFilteredEvents();
    renderEvents();
    updateNavigationCounts();
    
    // Re-render calendar if it's currently visible
    if (calendarView.style.display !== 'none') {
        renderCalendar();
    }
}

// Toggle venue filter
function toggleVenueFilter(venue) {
    console.log('Toggling venue filter:', venue); // Debug log
    console.log('Selected venues before:', [...selectedVenues]); // Debug log
    
    if (venue === 'all') {
        selectedVenues.clear();
        document.querySelectorAll('.venue-filter-btn').forEach(btn => {
            btn.classList.remove('active');
        });
        document.querySelector('.venue-filter-btn').classList.add('active'); // "All" button
    } else {
        // Remove "All" selection
        document.querySelector('.venue-filter-btn').classList.remove('active');
        
        const button = [...document.querySelectorAll('.venue-filter-btn')]
            .find(btn => btn.textContent === getVenueName(venue));
        
        console.log('Found button:', button?.textContent); // Debug log
        
        if (selectedVenues.has(venue)) {
            selectedVenues.delete(venue);
            if (button) button.classList.remove('active');
        } else {
            selectedVenues.add(venue);
            if (button) button.classList.add('active');
        }
        
        // If no venues selected, activate "All"
        if (selectedVenues.size === 0) {
            document.querySelector('.venue-filter-btn').classList.add('active');
        }
    }
    
    console.log('Selected venues after:', [...selectedVenues]); // Debug log
    
    updateFilteredEvents();
    renderEvents();
    updateNavigationCounts();
    
    // Re-render calendar if it's currently visible
    if (calendarView.style.display !== 'none') {
        renderCalendar();
    }
}

// Update filtered movies based on current rating and genre filters
function updateFilteredEvents() {
    const minRating = parseInt(ratingSlider.value);
    
    filteredEvents = eventsData.filter(movie => {
        // Rating filter
        if (movie.rating < minRating) return false;
        
        // Country filter
        if (selectedGenres.size > 0 && !selectedGenres.has(movie.country)) {
            return false;
        }
        
        // Venue filter
        if (selectedVenues.size > 0 && !selectedVenues.has(movie.venue)) {
            return false;
        }

        // Special events filter
        if (showSpecialEventsOnly && !movie.isSpecialScreening) {
            return false;
        }

        // Work hours filter
        if (hideWorkHours && movie.isWorkHours) {
            return false;
        }

        // Director filter
        if (selectedDirector && movie.director !== selectedDirector) {
            return false;
        }

        // Search filter (title, director, one-liner, description)
        if (searchTerm) {
            const fields = [
                movie.title,
                movie.director,
                movie.oneLinerSummary,
                movie.description,
            ];
            const haystack = fields
                .filter(Boolean)
                .join(' ') // combine fields
                .toLowerCase();
            if (!haystack.includes(searchTerm)) {
                return false;
            }
        }

        // Date range filter
        if (dateRangeStart && dateRangeEnd) {
            if (!movie.screenings || !Array.isArray(movie.screenings)) return false;
            const hasScreeningInRange = movie.screenings.some(screening => {
                const screeningDate = parseLocalDate(screening.date);
                // Compare dates at same time of day
                screeningDate.setHours(0, 0, 0, 0);
                const startCompare = new Date(dateRangeStart);
                startCompare.setHours(0, 0, 0, 0);
                const endCompare = new Date(dateRangeEnd);
                endCompare.setHours(0, 0, 0, 0);  // Changed to start of end day
                const inRange = screeningDate >= startCompare && screeningDate < endCompare;
                return inRange;
            });
            if (!hasScreeningInRange) return false;
        }
        
        return true;
    });
    
    updateDownloadButton();
}

// Update download button state
function updateDownloadButton() {
    const count = filteredEvents.length;
    if (count === 0) {
        downloadBtn.textContent = 'No events match criteria';
        downloadBtn.disabled = true;
    } else {
        downloadBtn.textContent = `Download Calendar (${count} events)`;
        downloadBtn.disabled = false;
    }
}

// Helper function to get earliest screening date for sorting
function getEarliestScreeningDate(movie) {
    if (!movie.screenings || movie.screenings.length === 0) {
        return new Date('2099-12-31'); // Far future date for events without screenings
    }

    const dates = movie.screenings.map(screening => new Date(screening.date));
    return new Date(Math.min(...dates.map(d => d.getTime())));
}

// Render movies list
function renderEvents() {
    // Always use filteredEvents when filters are active
    let moviesToRender = filteredEvents;
    
    if (moviesToRender.length === 0) {
        eventsList.innerHTML = '<p class="no-events">No events match the current filters.</p>';
        updateEventCount();
        return;
    }

    // Sort movies based on current sort option
    moviesToRender = [...moviesToRender].sort((a, b) => {
        if (currentSort === 'rating') {
            // Sort by rating (high to low)
            return (b.final_rating || b.rating || 0) - (a.final_rating || a.rating || 0);
        } else {
            // Sort chronologically (earliest first)
            const aDate = getEarliestScreeningDate(a);
            const bDate = getEarliestScreeningDate(b);
            return aDate - bDate;
        }
    });

    eventsList.innerHTML = moviesToRender.map(event => createEventCard(event)).join('');
    
    // Update the event count
    updateEventCount();
}

// Create HTML for a movie card (newspaper style)
function createEventCard(event) {
    // Safety checks for required properties
    if (!event || !event.title) {
        console.error('Invalid event object:', event);
        return '<article class="event-card error">Invalid event data</article>';
    }
    
    // Always use unified compact layout
    
    // Extract key data with improved rating handling
    const finalRating = event.final_rating ?? event.rating ?? (event.ai_rating ? event.ai_rating.score : null);
    const eventUrl = event.screenings && event.screenings[0] ? event.screenings[0].url : (event.url || '#');
    
    // Debug rating values to identify issues
    console.log(`Event: ${event.title}, final_rating: ${event.final_rating}, rating: ${event.rating}, ai_rating: ${event.ai_rating ? JSON.stringify(event.ai_rating) : 'null'}, finalRating: ${finalRating}`);
    
    // Format date and venue
    let datelineText = '';
    let compactDateTime = '';
    if (event.screenings && event.screenings.length > 0) {
        const firstScreening = event.screenings[0];
        const date = parseLocalDate(firstScreening.date);
        // Ensure we're using local timezone for display
        const dateOptions = { weekday: 'short', month: 'short', day: 'numeric', timeZone: 'America/Chicago' };
        const formattedDate = date.toLocaleDateString('en-US', dateOptions).toUpperCase();
        const time = firstScreening.time || '';
        const venue = getVenueName(event.venue).toUpperCase();
        datelineText = `${venue} — ${formattedDate}${time ? ' AT ' + time : ''}`;
        
        // Compact format: "Thu, Jul 3 · 3:30 PM · Austin Film Society"
        const compactDateOptions = { weekday: 'short', month: 'short', day: 'numeric', timeZone: 'America/Chicago' };
        const compactDate = date.toLocaleDateString('en-US', compactDateOptions);
        compactDateTime = `${compactDate} · ${time} · ${getVenueName(event.venue)}`;
    }
    
    // Get oneLinerSummary or truncated description
    const summary = event.oneLinerSummary || truncateText(stripHtmlTags(event.description || ''), 150);
    
    // Build metadata string
    const metaParts = [];
    if (event.director) metaParts.push(event.director);
    if (event.year) metaParts.push(event.year);
    if (event.duration) metaParts.push(event.duration);
    const metadata = metaParts.join(' | ');
    
    // Always allow review access - every event is clickable
    
    // Unified compact layout with premium typography
    return `
        <article class="event-card" onclick="openReviewModal('${event.id || 'unknown'}')" style="cursor: pointer;">
            <div class="wireframe-line1">
                <h3 class="event-card-title"><a href="${eventUrl}" target="_blank" rel="noopener" onclick="event.stopPropagation()">${escapeHtml(event.title)}</a></h3>
            </div>
            <div class="wireframe-line2">
                <div class="event-meta">${compactDateTime} — ${metadata}</div>
            </div>
            <div class="wireframe-line3">
                <div class="event-summary">${escapeHtml(summary)} ${finalRating && finalRating > 0 ? `(★ ${finalRating}/10)` : '(Rating: N/A)'}</div>
                <button class="premium-review-link" onclick="event.stopPropagation(); openReviewModal('${event.id || 'unknown'}')" aria-label="Read detailed review for ${escapeHtml(event.title)}" style="background: none; border: none; color: #2563eb; cursor: pointer; text-decoration: underline; font-style: italic; margin-left: 0.5rem;">Read Review</button>
            </div>
        </article>
    `;
}

// Toggle review visibility
function toggleReview(eventId) {
    const reviewContent = document.getElementById(`review-${eventId}`);
    if (reviewContent) {
        const isVisible = reviewContent.style.display !== 'none';
        reviewContent.style.display = isVisible ? 'none' : 'block';
        
        // Update button text
        const button = reviewContent.previousElementSibling;
        if (button && button.classList.contains('read-review-btn')) {
            button.textContent = isVisible ? 'Read Review →' : 'Hide Review';
        }
    }
}

// Toggle event details for compact cards
function toggleEventDetails(eventId) {
    const detailsContent = document.getElementById(`details-${eventId}`);
    if (detailsContent) {
        const isVisible = detailsContent.style.display !== 'none';
        detailsContent.style.display = isVisible ? 'none' : 'block';
    }
}

// Toggle description expansion
function toggleDescription(eventId) {
    const preview = document.getElementById(`preview-${eventId}`);
    const full = document.getElementById(`full-${eventId}`);
    const buttons = document.querySelectorAll(`[data-event-id="${eventId}"]`);

    if (full.classList.contains('expanded')) {
        // Collapse
        full.classList.remove('expanded');
        preview.style.display = 'block';
        buttons.forEach(btn => {
            if (btn.classList.contains('collapse-button')) {
                btn.style.display = 'none';
                btn.textContent = 'Hide';
            } else {
                btn.textContent = 'Show More';
            }
        });
    } else {
        // Expand
        full.classList.add('expanded');
        preview.style.display = 'none';
        buttons.forEach(btn => {
            if (btn.classList.contains('collapse-button')) {
                btn.style.display = 'inline';
                btn.textContent = 'Hide';
            } else {
                btn.textContent = 'Show Less';
            }
        });
    }
}

// Calendar navigation functions
function navigateMonth(direction) {
    currentMonth += direction;
    if (currentMonth > 11) {
        currentMonth = 0;
        currentYear++;
    } else if (currentMonth < 0) {
        currentMonth = 11;
        currentYear--;
    }
    renderCalendar();
}

function updateMonthYearDisplay() {
    const monthNames = ['January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'];
    monthYearDisplay.textContent = `${monthNames[currentMonth]} ${currentYear}`;
}

function applyDateRangeFilter() {
    const startDate = startDateInput.value;
    const endDate = endDateInput.value;
    
    if (startDate && endDate) {
        dateRangeStart = parseLocalDate(startDate);
        dateRangeEnd = parseLocalDate(endDate);
        updateFilteredEvents();
        renderEvents();
        updateNavigationCounts();
        if (calendarView.style.display !== 'none') {
            renderCalendar();
        }
    }
}

function clearDateRangeFilter() {
    dateRangeStart = null;
    dateRangeEnd = null;
    startDateInput.value = '';
    endDateInput.value = '';
    updateFilteredEvents();
    renderEvents();
    updateNavigationCounts();
    if (calendarView.style.display !== 'none') {
        renderCalendar();
    }
}

// Render calendar view
function renderCalendar() {
    console.log('Rendering calendar...'); // Debug log
    
    if (!eventsData || eventsData.length === 0) {
        console.log('No event data available for calendar');
        calendarContainer.innerHTML = '<p>No event data available</p>';
        return;
    }
    
    updateMonthYearDisplay();
    const today = new Date();
    
    // Get screenings from filtered movies (respects UI filters)
    const moviesToUse = filteredEvents.length > 0 ? filteredEvents : eventsData;
    const allScreenings = [];
    moviesToUse.forEach(movie => {
        if (movie.screenings && Array.isArray(movie.screenings)) {
            movie.screenings.forEach(screening => {
                allScreenings.push({
                    date: screening.date,
                    time: screening.time,
                    url: screening.url,
                    title: movie.title,
                    rating: movie.rating,
                    venue: movie.venue,
                    id: movie.id
                });
            });
        }
    });
    
    console.log(`Found ${allScreenings.length} screenings after applying filters`); // Debug log
    
    // Create calendar header
    const monthNames = ['January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'];
    
    let calendarHTML = `
        <div class="calendar-header">
            ${monthNames[currentMonth]} ${currentYear}
        </div>
        <div class="calendar-grid">
            <div class="calendar-day-header">Sun</div>
            <div class="calendar-day-header">Mon</div>
            <div class="calendar-day-header">Tue</div>
            <div class="calendar-day-header">Wed</div>
            <div class="calendar-day-header">Thu</div>
            <div class="calendar-day-header">Fri</div>
            <div class="calendar-day-header">Sat</div>
    `;
    
    // Get first day of month
    const firstDay = new Date(currentYear, currentMonth, 1);
    const startDate = new Date(firstDay);
    startDate.setDate(startDate.getDate() - firstDay.getDay());
    
    // Generate calendar days (6 weeks = 42 days)
    for (let i = 0; i < 42; i++) {
        const currentDate = new Date(startDate.getTime() + (i * 24 * 60 * 60 * 1000));
        const dateStr = formatDateForComparison(currentDate);
        const isCurrentMonth = currentDate.getMonth() === currentMonth;
        const isToday = dateStr === formatDateForComparison(today);
        
        // Find screenings for this date
        const dayScreenings = allScreenings.filter(s => s.date === dateStr);
        
        let dayClass = 'calendar-day';
        if (!isCurrentMonth) dayClass += ' other-month';
        if (isToday) dayClass += ' today';
        
        let eventsHTML = '';
        dayScreenings.forEach(screening => {
            const ratingClass = screening.rating >= 8 ? 'high-rating' : 
                              screening.rating >= 6 ? 'medium-rating' : 'low-rating';
            
            // Get venue abbreviation and CSS class for visual indication
            const venueAbbr = getVenueAbbr(screening.venue);
            const venueClass = screening.venue ? `venue-${screening.venue.toLowerCase()}` : '';
            
            // Truncate long movie titles for calendar display
            const displayTitle = screening.title.length > 15 ? 
                screening.title.substring(0, 12) + '...' : screening.title;
            
            eventsHTML += `
                <div class="calendar-event ${ratingClass} ${venueClass}" 
                     title="${escapeHtml(screening.title)} - ${screening.time} - Rating: ${screening.rating}/10 - ${getVenueName(screening.venue)}"
                     onclick="window.open('${screening.url}', '_blank')">
                    ${venueAbbr} ★${screening.rating} ${escapeHtml(displayTitle)}
                </div>
            `;
        });
        
        calendarHTML += `
            <div class="${dayClass}">
                <div class="calendar-date">${currentDate.getDate()}</div>
                <div class="calendar-events">${eventsHTML}</div>
            </div>
        `;
    }
    
    calendarHTML += '</div>';
    
    try {
        calendarContainer.innerHTML = calendarHTML;
        console.log('Calendar rendered successfully');
    } catch (error) {
        console.error('Error setting calendar HTML:', error);
        calendarContainer.innerHTML = '<p>Error rendering calendar</p>';
    }
}

// Helper function to format date for comparison (YYYY-MM-DD)
function formatDateForComparison(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

// Add to Google Calendar function

// Helper function to get filtered movies for download
function getFilteredEventsForDownload(minRating) {
    return eventsData.filter(event => {
        // Rating filter
        if (event.rating < minRating) return false;
        
        // Country filter
        if (selectedGenres.size > 0 && !selectedGenres.has(event.country)) {
            return false;
        }
        
        // Venue filter
        if (selectedVenues.size > 0 && !selectedVenues.has(event.venue)) {
            return false;
        }
        
        // Special events filter
        if (showSpecialEventsOnly && !event.isSpecialScreening) {
            return false;
        }

        // Director filter
        if (selectedDirector && event.director !== selectedDirector) {
            return false;
        }

        // Search filter
        if (searchTerm) {
            const fields = [
                event.title,
                event.director,
                event.oneLinerSummary,
                event.description,
            ];
            const haystack = fields
                .filter(Boolean)
                .join(' ')
                .toLowerCase();
            if (!haystack.includes(searchTerm)) {
                return false;
            }
        }

        // Date range filter
        if (dateRangeStart && dateRangeEnd) {
            if (!event.screenings || !Array.isArray(event.screenings)) return false;
            const hasScreeningInRange = event.screenings.some(screening => {
                const screeningDate = parseLocalDate(screening.date);
                return screeningDate >= dateRangeStart && screeningDate <= dateRangeEnd;
            });
            if (!hasScreeningInRange) return false;
        }
        
        return true;
    });
}

// Download filtered calendar
function downloadFilteredCalendar(minRating) {
    const filteredEvents = getFilteredEventsForDownload(minRating);
    
    if (filteredEvents.length === 0) {
        alert('No events match the selected filters.');
        return;
    }
    
    // Convert aggregated movies back to individual screenings for ICS
    const screenings = [];
    filteredEvents.forEach(movie => {
        if (movie.screenings && Array.isArray(movie.screenings)) {
            movie.screenings.forEach(screening => {
                // Guard against missing screening data
                if (!screening || !screening.date) return;

                const timeString = screening.time || '';

                screenings.push({
                    title: movie.title,
                    date: screening.date,
                    time: timeString,
                    description: movie.description,
                    rating: movie.rating,
                    url: screening.url,
                    id: `${movie.id || 'event'}-${screening.date}-${timeString.replace(/[^0-9]/g, '')}`
                });
            });
        }
    });
    
    // Generate calendar content
    const icsContent = generateICSContent(screenings);
    
    // Create and trigger download
    const blob = new Blob([icsContent], { type: 'text/calendar;charset=utf-8' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    
    // Generate filename with filters
    const countryFilter = selectedGenres.size > 0 ? `-${[...selectedGenres].join('-')}` : '';
    const venueFilter = selectedVenues.size > 0 ? `-${[...selectedVenues].join('-')}` : '';
    const specialFilter = showSpecialEventsOnly ? '-special' : '';
    const dateFilter = dateRangeStart && dateRangeEnd ? `-${formatDateForFilename(dateRangeStart)}-to-${formatDateForFilename(dateRangeEnd)}` : '';
    link.download = `culture-calendar-${minRating}plus${countryFilter}${venueFilter}${specialFilter}${dateFilter}-${getCurrentDateString()}.ics`;
    
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

// Generate ICS calendar content
function generateICSContent(movies) {
    const now = new Date();
    const timestamp = now.toISOString().replace(/[-:]/g, '').split('.')[0] + 'Z';
    
    let icsContent = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//Culture Calendar//Austin Film Society Events//EN',
        'CALSCALE:GREGORIAN',
        'METHOD:PUBLISH',
        'X-WR-CALDESC:Curated film screenings from Austin Film Society',
        'X-WR-CALNAME:Culture Calendar - Austin Film Society',
        'BEGIN:VTIMEZONE',
        'TZID:America/Chicago',
        'BEGIN:STANDARD',
        'DTSTART:20071104T020000',
        'RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU',
        'TZNAME:CST',
        'TZOFFSETFROM:-0500',
        'TZOFFSETTO:-0600',
        'END:STANDARD',
        'BEGIN:DAYLIGHT',
        'DTSTART:20070311T020000',
        'RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU',
        'TZNAME:CDT',
        'TZOFFSETFROM:-0600',
        'TZOFFSETTO:-0500',
        'END:DAYLIGHT',
        'END:VTIMEZONE',
        ''
    ].join('\r\n');
    
    movies.forEach(event => {
        const startDateTime = formatDateTimeForICS(event.date, event.time);
        const endDateTime = formatDateTimeForICS(event.date, event.time, 2); // 2 hour duration
        
        icsContent += [
            'BEGIN:VEVENT',
            `UID:${event.id}@culturecalendar.local`,
            `DTSTAMP:${timestamp}`,
            `DTSTART;${startDateTime}`,
            `DTEND;${endDateTime}`,
            `SUMMARY:★${event.rating}/10 - ${event.title}`,
            `DESCRIPTION:${formatDescriptionForICS(event.description)}`,
            `LOCATION:Austin Film Society Cinema, 6226 Middle Fiskville Rd, Austin, TX 78752`,
            `URL:${event.url || 'https://www.austinfilm.org/'}`,
            'CATEGORIES:Film,Entertainment',
            'END:VEVENT',
            ''
        ].join('\r\n');
    });
    
    icsContent += 'END:VCALENDAR\r\n';
    return icsContent;
}

// Utility functions
function getVenueName(venue) {
    const venueNames = {
        'AFS': 'Austin Film Society',
        'Hyperreal': 'Hyperreal Film Club',
        'Paramount': 'Paramount Theater',
        'Symphony': 'Austin Symphony',
        'EarlyMusic': 'Early Music Project',
        'LaFollia': 'La Follia Austin',
        'BalletAustin': 'Ballet Austin',
        'AlienatedMajesty': 'Alienated Majesty Books',
        'FirstLight': 'First Light Austin',
        'NewYorkerMeetup': 'New Yorker Book Club'
    };
    return venueNames[venue] || venue;
}

function getVenueAbbr(venue) {
    const venueAbbrs = {
        'AFS': 'AFS',
        'Hyperreal': 'HFC',
        'Paramount': 'PAR',
        'Symphony': 'ASO',
        'EarlyMusic': 'EMP',
        'LaFollia': 'LFA',
        'BalletAustin': 'BAL',
        'AlienatedMajesty': 'AMB',
        'FirstLight': 'FLA',
        'NewYorkerMeetup': 'NYR'
    };
    return venueAbbrs[venue] || venue;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function truncateText(text, maxLength) {
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength).trim() + '...';
}

function formatDescription(text) {
    // For plain text, convert line breaks to HTML and handle basic formatting
    return text.replace(/\n/g, '<br>').replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
}

function stripHtmlTags(html) {
    const div = document.createElement('div');
    div.innerHTML = html;
    return div.textContent || div.innerText || '';
}

function formatDescriptionForICS(text) {
    // Escape special characters for ICS format
    return text.replace(/\\/g, '\\\\')
               .replace(/;/g, '\\;')
               .replace(/,/g, '\\,')
               .replace(/\n/g, '\\n')
               .replace(/\r/g, '');
}

function parseLocalDate(dateStr) {
    const parts = dateStr.split('-').map(Number);
    // Create date at noon to avoid timezone issues
    return new Date(parts[0], parts[1] - 1, parts[2], 12, 0, 0);
}

function formatDate(dateStr) {
    const date = parseLocalDate(dateStr);
    return date.toLocaleDateString('en-US', {
        weekday: 'short',
        month: 'short',
        day: 'numeric'
    });
}

function formatDateTimeForICS(dateStr, timeStr, hoursToAdd = 0) {
    const date = parseLocalDate(dateStr);
    
    // Parse time
    const timeMatch = timeStr.match(/(\d{1,2}):(\d{2})\s*(AM|PM)/i);
    if (timeMatch) {
        let hours = parseInt(timeMatch[1]);
        const minutes = parseInt(timeMatch[2]);
        const ampm = timeMatch[3].toUpperCase();
        
        if (ampm === 'PM' && hours !== 12) hours += 12;
        if (ampm === 'AM' && hours === 12) hours = 0;
        
        date.setHours(hours + hoursToAdd, minutes, 0, 0);
    }
    
    // Format for Austin timezone using TZID=America/Chicago
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    const seconds = String(date.getSeconds()).padStart(2, '0');
    
    return `TZID=America/Chicago:${year}${month}${day}T${hours}${minutes}${seconds}`;
}

function getCurrentDateString() {
    const now = new Date();
    return now.toISOString().split('T')[0].replace(/-/g, '');
}

function formatDateForFilename(date) {
    return date.toISOString().split('T')[0].replace(/-/g, '');
}

function hideLoading() {
    loadingElement.style.display = 'none';
}

function showError(message) {
    loadingElement.innerHTML = `<p class="error">⚠️ ${message}</p>`;
}

// Check if classical music data is outdated
function checkClassicalDataFreshness() {
    // Find all classical music events (Symphony, EarlyMusic, LaFollia venues)
    const classicalVenues = ['Symphony', 'EarlyMusic', 'LaFollia'];
    const classicalEvents = eventsData.filter(event => 
        event.screenings && event.screenings.some(screening => 
            classicalVenues.includes(screening.venue)
        )
    );
    
    if (classicalEvents.length === 0) {
        console.log('No classical music events found in data');
        return;
    }
    
    // Find the latest date among all classical events
    let latestClassicalDate = null;
    const today = new Date();
    
    classicalEvents.forEach(event => {
        event.screenings.forEach(screening => {
            if (classicalVenues.includes(screening.venue)) {
                const eventDate = parseLocalDate(screening.date);
                if (!latestClassicalDate || eventDate > latestClassicalDate) {
                    latestClassicalDate = eventDate;
                }
            }
        });
    });
    
    // Check if all classical events are in the past
    if (latestClassicalDate && latestClassicalDate < today) {
        showClassicalDataWarning();
    }
}

// Show warning about outdated classical music data
function showClassicalDataWarning() {
    const warningContainer = document.getElementById('classical-data-warning');
    if (!warningContainer) {
        console.warn('Classical data warning container not found');
        return;
    }
    
    const currentYear = new Date().getFullYear();
    const nextYear = currentYear + 1;
    
    warningContainer.innerHTML = `
        <div class="warning-content">
            <h3>⚠️ Classical Music Season Update Needed</h3>
            <p>The classical music season data appears to be outdated. All concerts in the database have already passed.</p>
            <p><strong>Action needed:</strong> Please update the classical music data for the ${nextYear}/${nextYear + 1} season.</p>
            <div class="venue-links">
                <p><strong>Update sources:</strong></p>
                <ul>
                    <li><a href="https://austinsymphony.org/concerts/" target="_blank" rel="noopener">Austin Symphony Orchestra Season</a></li>
                    <li><a href="https://www.earlymusicaustin.org/concerts/" target="_blank" rel="noopener">Texas Early Music Project</a></li>
                    <li><a href="https://www.lafollia.com/concerts/" target="_blank" rel="noopener">La Follia Austin Chamber Music</a></li>
                </ul>
            </div>
            <p class="update-note">Update the data in <code>docs/classical_data.json</code> with the new season information.</p>
        </div>
    `;
    
    warningContainer.style.display = 'block';
    console.log('Classical music data warning displayed');
}

// Premium Review Modal System
// =============================================================================

class ReviewModal {
    constructor(config = {}) {
        this.config = {
            backdrop: 'blur',
            closeOnBackdrop: true,
            closeOnEscape: true,
            animation: 'scale',
            duration: 300,
            ...config
        };
        
        this.isModalOpen = false;
        this.focusedElementBeforeModal = null;
        this.modal = null;
        this.focusableElements = [];
        
        // Bind methods
        this.handleKeydown = this.handleKeydown.bind(this);
        this.handleBackdropClick = this.handleBackdropClick.bind(this);
    }

    async open(eventData) {
        if (this.isModalOpen) return;
        
        console.log('Opening modal for event:', eventData.title);
        
        // Store focus reference
        this.focusedElementBeforeModal = document.activeElement;
        
        // Create and inject modal
        this.createModal(eventData);
        document.body.appendChild(this.modal);
        
        // Prevent body scroll
        document.body.style.overflow = 'hidden';
        
        // Setup event listeners
        this.setupEventListeners();
        
        // Trigger opening animation
        await this.animateOpen();
        
        // Setup focus trap
        this.setupFocusTrap();
        
        this.isModalOpen = true;
        
        // Announce to screen readers
        this.announceToScreenReader(`Review modal opened for ${eventData.title}`);
    }

    async close() {
        if (!this.isModalOpen) return;
        
        console.log('Closing modal');
        
        // Animate close
        await this.animateClose();
        
        // Cleanup
        this.cleanup();
        
        this.isModalOpen = false;
        
        // Announce to screen readers
        this.announceToScreenReader('Review modal closed');
    }

    createModal(eventData) {
        this.modal = document.createElement('div');
        this.modal.className = 'review-modal';
        this.modal.setAttribute('role', 'dialog');
        this.modal.setAttribute('aria-modal', 'true');
        this.modal.setAttribute('aria-labelledby', 'modal-title');
        
        this.modal.innerHTML = this.getModalHTML(eventData);
    }

    getModalHTML(eventData) {
        const rating = eventData.final_rating ?? eventData.rating ?? (eventData.ai_rating ? eventData.ai_rating.score : null);
        const ratingDisplay = rating ? `★${rating}/10` : '';
        
        return `
            <div class="review-modal-container">
                <div class="review-modal-content">
                    <div class="review-modal-header">
                        <h2 id="modal-title" class="review-modal-title">${escapeHtml(eventData.title)}</h2>
                        <div class="review-modal-actions">
                            <button class="review-modal-close" aria-label="Close review modal">×</button>
                        </div>
                    </div>
                    <div class="review-modal-body">
                        ${rating ? `<div class="event-rating" style="margin-bottom: 1.5rem;">
                            <span class="star">★</span>${rating}/10
                        </div>` : ''}
                        <div class="review-content">
                            ${eventData.description ? formatDescription(eventData.description) : 'No detailed review available for this event.'}
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    async animateOpen() {
        return new Promise(resolve => {
            // Start invisible but present
            this.modal.style.opacity = '0';
            this.modal.style.visibility = 'visible';
            
            requestAnimationFrame(() => {
                this.modal.classList.add('active');
                setTimeout(resolve, this.config.duration);
            });
        });
    }

    async animateClose() {
        return new Promise(resolve => {
            this.modal.classList.remove('active');
            
            setTimeout(() => {
                resolve();
            }, this.config.duration);
        });
    }

    setupEventListeners() {
        // Close button
        const closeButton = this.modal.querySelector('.review-modal-close');
        closeButton.addEventListener('click', () => this.close());
        
        // Backdrop click
        this.modal.addEventListener('click', this.handleBackdropClick);
        
        // Keyboard events
        document.addEventListener('keydown', this.handleKeydown);
    }

    handleBackdropClick(event) {
        if (this.config.closeOnBackdrop && event.target === this.modal) {
            this.close();
        }
    }

    handleKeydown(event) {
        if (!this.isModalOpen) return;
        
        if (event.key === 'Escape' && this.config.closeOnEscape) {
            this.close();
            return;
        }
        
        if (event.key === 'Tab') {
            this.trapFocus(event);
        }
    }

    setupFocusTrap() {
        this.focusableElements = Array.from(
            this.modal.querySelectorAll(
                'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
            )
        );
        
        if (this.focusableElements.length > 0) {
            this.focusableElements[0].focus();
        }
    }

    trapFocus(event) {
        if (this.focusableElements.length === 0) return;
        
        const firstFocusable = this.focusableElements[0];
        const lastFocusable = this.focusableElements[this.focusableElements.length - 1];
        
        if (event.shiftKey) {
            if (document.activeElement === firstFocusable) {
                lastFocusable.focus();
                event.preventDefault();
            }
        } else {
            if (document.activeElement === lastFocusable) {
                firstFocusable.focus();
                event.preventDefault();
            }
        }
    }

    cleanup() {
        // Remove event listeners
        document.removeEventListener('keydown', this.handleKeydown);
        
        // Restore body scroll
        document.body.style.overflow = '';
        
        // Remove modal from DOM
        if (this.modal && this.modal.parentNode) {
            document.body.removeChild(this.modal);
        }
        
        // Restore focus
        if (this.focusedElementBeforeModal) {
            this.focusedElementBeforeModal.focus();
        }
        
        this.modal = null;
        this.focusableElements = [];
    }

    announceToScreenReader(message) {
        const announcement = document.createElement('div');
        announcement.setAttribute('aria-live', 'polite');
        announcement.setAttribute('aria-atomic', 'true');
        announcement.className = 'sr-only';
        announcement.textContent = message;
        
        document.body.appendChild(announcement);
        
        setTimeout(() => {
            if (document.body.contains(announcement)) {
                document.body.removeChild(announcement);
            }
        }, 1000);
    }
}

// Global modal instance
const globalReviewModal = new ReviewModal();

// Enhanced review modal trigger function
function openReviewModal(eventId) {
    console.log('Opening modal for event ID:', eventId);
    console.log('Available events:', eventsData.map(e => ({ id: e.id, title: e.title })));
    
    const event = eventsData.find(e => e.id === eventId);
    if (event) {
        console.log('Found event:', event.title);
        // Always open modal - it will show whatever content is available
        globalReviewModal.open(event);
    } else {
        console.error('Event not found for ID:', eventId);
        console.log('Available event IDs:', eventsData.map(e => e.id));
        // Show a fallback modal with error message
        alert(`Sorry, could not find review for event ID: ${eventId}`);
    }
}

// Keep the existing toggleReview function for backward compatibility
// But enhance it to use the modal for long reviews
function toggleReview(eventId) {
    const event = eventsData.find(e => e.id === eventId);
    if (event && event.description && event.description.length > 200) {
        // Use modal for long reviews
        globalReviewModal.open(event);
    } else {
        // Use original inline toggle for short reviews
        const reviewContent = document.getElementById(`review-${eventId}`);
        if (reviewContent) {
            const isVisible = reviewContent.style.display !== 'none';
            reviewContent.style.display = isVisible ? 'none' : 'block';
            
            // Update button text
            const button = reviewContent.previousElementSibling;
            if (button && button.classList.contains('read-review-btn')) {
                button.textContent = isVisible ? 'Read Review →' : 'Hide Review';
            }
        }
    }
}