// Global variables
let moviesData = [];
let filteredMovies = [];
let selectedGenres = new Set();
let selectedVenues = new Set();
let showSpecialEventsOnly = false;
let currentMonth = new Date().getMonth();
let currentYear = new Date().getFullYear();
let dateRangeStart = null;
let dateRangeEnd = null;
let currentSort = 'chronological';
let currentNavFilter = 'all';

// DOM elements
const ratingSlider = document.getElementById('rating-slider');
const ratingValue = document.getElementById('rating-value');
const downloadBtn = document.getElementById('download-btn');
const moviesList = document.getElementById('movies-list');
const loadingElement = document.getElementById('loading');
const listViewBtn = document.getElementById('list-view-btn');
const calendarViewBtn = document.getElementById('calendar-view-btn');
const listView = document.getElementById('list-view');
const calendarView = document.getElementById('calendar-view');
const calendarContainer = document.getElementById('calendar-container');
const specialEventsToggle = document.getElementById('special-events-toggle');
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
const refineBtn = document.getElementById('refine-btn');
const filterDrawer = document.getElementById('filter-drawer');
const sortBtn = document.getElementById('sort-btn');
const sortMenu = document.getElementById('sort-menu');
const navLinks = document.querySelectorAll('.nav-link');

let searchTerm = '';
let selectedDirector = null;

// Initialize the app
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM Content Loaded'); // Debug log
    
    // Verify critical elements exist
    const criticalElements = ['loading', 'movies-list', 'rating-slider'];
    const missingElements = criticalElements.filter(id => !document.getElementById(id));
    
    if (missingElements.length > 0) {
        console.error('Missing critical elements:', missingElements);
        alert('Page not loaded properly. Missing elements: ' + missingElements.join(', '));
        return;
    }
    
    console.log('All critical elements found, proceeding...'); // Debug log
    setupEventListeners();
    loadMoviesData();
    loadUpdateInfo();
    loadCodeUpdateTime();
});

// Set up event listeners
function setupEventListeners() {
    ratingSlider.addEventListener('input', function() {
        ratingValue.textContent = this.value;
        updateFilteredMovies();
        renderMovies();
        
        // Re-render calendar if it's currently visible
        if (calendarView.style.display !== 'none') {
            renderCalendar();
        }
    });

    downloadBtn.addEventListener('click', function() {
        const minRating = parseInt(ratingSlider.value);
        downloadFilteredCalendar(minRating);
    });

    if (listViewBtn) {
        listViewBtn.addEventListener('click', function() {
            switchToListView();
        });
    }

    if (calendarViewBtn) {
        calendarViewBtn.addEventListener('click', function() {
            switchToCalendarView();
        });
    }

    specialEventsToggle.addEventListener('click', function() {
        toggleSpecialEventsFilter();
    });

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
            updateFilteredMovies();
            renderMovies();
            if (calendarView.style.display !== 'none') {
                renderCalendar();
            }
        });
    }

    if (refineBtn) {
        refineBtn.addEventListener('click', function() {
            toggleFilterDrawer();
        });
    }

    // Sort functionality
    if (sortBtn) {
        sortBtn.addEventListener('click', function() {
            toggleSortMenu();
        });
    }

    // Navigation functionality
    navLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            const linkText = this.textContent.toLowerCase();
            handleNavClick(linkText, this);
        });
    });

    // Sort options
    document.addEventListener('click', function(e) {
        if (e.target.classList.contains('sort-option')) {
            handleSortChange(e.target.dataset.sort);
        }
        // Close sort menu if clicking outside
        if (!e.target.closest('.sort-dropdown')) {
            closeSortMenu();
        }
    });
}

// Sort menu functions
function toggleSortMenu() {
    sortMenu.classList.toggle('open');
}

function closeSortMenu() {
    sortMenu.classList.remove('open');
}

function handleSortChange(sortType) {
    currentSort = sortType;
    
    // Update active sort option
    document.querySelectorAll('.sort-option').forEach(option => {
        option.classList.remove('active');
    });
    document.querySelector(`[data-sort="${sortType}"]`).classList.add('active');
    
    // Re-render movies with new sort
    renderMovies();
    closeSortMenu();
}

// Navigation functions
function handleNavClick(linkText, element) {
    // Update active nav link
    navLinks.forEach(link => link.classList.remove('active'));
    element.classList.add('active');
    
    // Set navigation filter
    currentNavFilter = linkText;
    
    // Handle different navigation types
    switch (linkText) {
        case 'today':
            filterToday();
            break;
        case 'this week':
            filterThisWeek();
            break;
        case 'weekend':
        case 'this weekend':
            filterThisWeekend();
            break;
        case 'calendar':
            clearDateRangeFilter();
            switchToCalendarView();
            break;
        case 'venues':
            // Show venue filter in drawer
            if (!filterDrawer.classList.contains('open')) {
                toggleFilterDrawer();
            }
            break;
        case 'all events':
            currentNavFilter = 'all';
            clearDateRangeFilter();
            updateFilteredMovies();
            renderMovies();
            const allHeader = document.querySelector('#list-view h2');
            if (allHeader) {
                allHeader.textContent = 'All Upcoming Events';
            }
            break;
        default:
            currentNavFilter = 'all';
            clearDateRangeFilter();
            updateFilteredMovies();
            renderMovies();
            // Reset section header
            const sectionHeader = document.querySelector('#list-view h2');
            if (sectionHeader) {
                sectionHeader.textContent = 'All Upcoming Events';
            }
    }
}

function filterToday() {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);
    
    dateRangeStart = today;
    dateRangeEnd = tomorrow;
    
    updateFilteredMovies();
    renderMovies();
    
    // Update section header
    const sectionHeader = document.querySelector('#list-view h2');
    if (sectionHeader) {
        sectionHeader.textContent = `Today's Events (${filteredMovies.length})`;
    }
    
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
    
    updateFilteredMovies();
    renderMovies();
    
    // Update section header
    const sectionHeader = document.querySelector('#list-view h2');
    if (sectionHeader) {
        sectionHeader.textContent = `This Week's Events (${filteredMovies.length})`;
    }
    
    // Switch to list view for better readability
    switchToListView();
}

function filterThisWeekend() {
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    // Determine Friday of the current week
    const friday = new Date(today);
    const day = friday.getDay();
    const diffToFriday = (5 - day + 7) % 7;
    friday.setDate(friday.getDate() + diffToFriday);

    const sunday = new Date(friday);
    sunday.setDate(friday.getDate() + 2);
    sunday.setHours(23, 59, 59, 999);

    dateRangeStart = friday;
    dateRangeEnd = sunday;

    updateFilteredMovies();
    renderMovies();

    const sectionHeader = document.querySelector('#list-view h2');
    if (sectionHeader) {
        sectionHeader.textContent = `This Weekend's Events (${filteredMovies.length})`;
    }

    switchToListView();
}

// Toggle filter drawer
function toggleFilterDrawer() {
    if (filterDrawer.classList.contains('open')) {
        filterDrawer.classList.remove('open');
        refineBtn.textContent = 'Refine Selection';
    } else {
        filterDrawer.classList.add('open');
        refineBtn.textContent = 'Hide Options';
    }
}

// Switch to list view
function switchToListView() {
    listView.style.display = 'block';
    calendarView.style.display = 'none';
    if (listViewBtn) listViewBtn.classList.add('active');
    if (calendarViewBtn) calendarViewBtn.classList.remove('active');
}

// Switch to calendar view
function switchToCalendarView() {
    console.log('Switching to calendar view...'); // Debug log
    
    try {
        listView.style.display = 'none';
        calendarView.style.display = 'block';
        if (listViewBtn) listViewBtn.classList.remove('active');
        if (calendarViewBtn) calendarViewBtn.classList.add('active');
        
        console.log('Movies data length:', moviesData.length); // Debug log
        
        if (moviesData && moviesData.length > 0) {
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
async function loadMoviesData() {
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
                moviesData = fallbackData;
            } else {
                throw new Error(`HTTP error! status: ${response.status} - ${response.statusText}`);
            }
        } else {
            moviesData = await response.json();
        }
        
        console.log('Loaded movies data:', moviesData?.length, 'events'); // Debug log
        
        // Validate data structure
        if (!Array.isArray(moviesData)) {
            console.error('Invalid data type:', typeof moviesData);
            throw new Error('Invalid data format: expected array, got ' + typeof moviesData);
        }
        
        // Check if we have valid event data
        if (moviesData.length === 0) {
            console.warn('No event data found');
            showError('No cultural events available at this time.');
            return;
        }
        
        console.log('Setting up filters...'); // Debug log
        setupGenreFilters();
        setupVenueFilters();
        updateFilteredMovies();
        renderMovies();
        filterToday();
        
        // Check for outdated classical music data
        checkClassicalDataFreshness();
        
        hideLoading();
        
        console.log('Movie data loaded successfully'); // Debug log
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
    const countries = [...new Set(moviesData
        .map(movie => movie.country)
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
    const venues = [...new Set(moviesData
        .map(movie => movie.venue)
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
    
    updateFilteredMovies();
    renderMovies();
    
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
    
    updateFilteredMovies();
    renderMovies();
    
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
    
    updateFilteredMovies();
    renderMovies();
    
    // Re-render calendar if it's currently visible
    if (calendarView.style.display !== 'none') {
        renderCalendar();
    }
}

// Update filtered movies based on current rating and genre filters
function updateFilteredMovies() {
    const minRating = parseInt(ratingSlider.value);
    
    filteredMovies = moviesData.filter(movie => {
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

        // Director filter
        if (selectedDirector && movie.director !== selectedDirector) {
            return false;
        }

        // Search filter (description)
        if (searchTerm) {
            const haystack = (movie.description || '').toLowerCase();
            if (!haystack.includes(searchTerm)) {
                return false;
            }
        }

        // Date range filter
        if (dateRangeStart && dateRangeEnd) {
            const hasScreeningInRange = movie.screenings.some(screening => {
                const screeningDate = parseLocalDate(screening.date);
                return screeningDate >= dateRangeStart && screeningDate <= dateRangeEnd;
            });
            if (!hasScreeningInRange) return false;
        }
        
        return true;
    });
    
    updateDownloadButton();
}

// Update download button state
function updateDownloadButton() {
    const count = filteredMovies.length;
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
function renderMovies() {
    let moviesToRender = filteredMovies.length > 0 ? filteredMovies : moviesData;
    
    if (moviesToRender.length === 0) {
        moviesList.innerHTML = '<p class="no-movies">No events match the current filters.</p>';
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

    moviesList.innerHTML = moviesToRender.map(movie => createMovieCard(movie)).join('');

    // Add event listeners for description toggle buttons
    document.querySelectorAll('.toggle-button').forEach(button => {
        button.addEventListener('click', function() {
            const movieId = this.dataset.movieId;
            toggleDescription(movieId);
        });
    });

    // Add click handlers for director badges
    document.querySelectorAll('.director-badge').forEach(span => {
        span.addEventListener('click', function() {
            const dir = this.dataset.director;
            if (selectedDirector === dir) {
                selectedDirector = null;
            } else {
                selectedDirector = dir;
            }
            updateFilteredMovies();
            renderMovies();
            if (calendarView.style.display !== 'none') {
                renderCalendar();
            }
        });
    });
}

// Create HTML for a movie card
function createMovieCard(movie) {
    // Safety checks for required properties
    if (!movie || !movie.title) {
        console.error('Invalid movie object:', movie);
        return '<div class="movie-card error">Invalid event data</div>';
    }
    
    const description = movie.description || 'No description available';
    const shortDescription = truncateText(stripHtmlTags(description), 200);
    const needsExpansion = stripHtmlTags(description).length > shortDescription.length;

    const finalRating = movie.final_rating ?? movie.rating ?? (movie.ai_rating ? movie.ai_rating.score : null);
    const aiRating = movie.ai_rating ? movie.ai_rating.score : finalRating;
    let boostHtml = '';
    if (finalRating && aiRating && finalRating > aiRating) {
        const boost = finalRating - aiRating;
        boostHtml = `<span class="preference-boost">+${boost}</span>`;
    }
    let stampHtml = '';
    if (finalRating && finalRating >= 8) {
        stampHtml = '<span class="quality-stamp">★</span>';
    }

    const metaParts = [];
    if (movie.director) metaParts.push(`Dir. ${escapeHtml(movie.director)}`);
    if (movie.country) metaParts.push(movie.country);
    if (movie.year) metaParts.push(movie.year);
    if (movie.language && movie.language !== 'English') metaParts.push(movie.language);
    if (movie.duration) metaParts.push(movie.duration);
    if (movie.venue) metaParts.push(getVenueName(movie.venue));
    const metaHtml = metaParts.length ? `<div class="movie-subtitle">${metaParts.join(' • ')}</div>` : '';

    // Create screening tags with safety check
    const screeningsText = (movie.screenings && Array.isArray(movie.screenings))
        ? movie.screenings.map(screening => {
            const formattedDate = formatDate(screening.date);
            const formattedTime = screening.time || 'Time TBA';
            return `${formattedDate} • ${formattedTime}`;
        }).join(' | ')
        : 'No screenings available';

    const eventUrl = movie.screenings && movie.screenings[0] ? movie.screenings[0].url : (movie.url || '#');
    
    return `
        <div class="movie-card">
            ${stampHtml}
            <div class="movie-header">
                <h3 class="movie-title"><a href="${eventUrl}" target="_blank">${escapeHtml(movie.title)}</a></h3>
                <div class="movie-rating">${finalRating || 'N/A'}/10 ${boostHtml}</div>
                ${needsExpansion ? `<button class="collapse-button toggle-button" data-movie-id="${movie.id || 'unknown'}" style="display:none">Hide</button>` : ''}
            </div>
            ${metaHtml}
            <div class="screenings-container">
                <div class="screenings-text">${screeningsText}</div>
                ${movie.isSpecialScreening ? '<span class="special-screening-indicator">Special Screening</span>' : ''}
            </div>

            <div class="movie-description">
                <div class="description-preview" id="preview-${movie.id || 'unknown'}">
                    ${formatDescription(shortDescription)}
                </div>
                <div class="description-full" id="full-${movie.id || 'unknown'}">
                    ${formatDescription(description)}
                </div>
                ${needsExpansion ? `
                    <button class="expand-button toggle-button" data-movie-id="${movie.id || 'unknown'}">
                        Show More
                    </button>
                ` : ''}
            </div>
        </div>
    `;
}

// Toggle description expansion
function toggleDescription(movieId) {
    const preview = document.getElementById(`preview-${movieId}`);
    const full = document.getElementById(`full-${movieId}`);
    const buttons = document.querySelectorAll(`[data-movie-id="${movieId}"]`);

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
        updateFilteredMovies();
        renderMovies();
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
    updateFilteredMovies();
    renderMovies();
    if (calendarView.style.display !== 'none') {
        renderCalendar();
    }
}

// Render calendar view
function renderCalendar() {
    console.log('Rendering calendar...'); // Debug log
    
    if (!moviesData || moviesData.length === 0) {
        console.log('No event data available for calendar');
        calendarContainer.innerHTML = '<p>No event data available</p>';
        return;
    }
    
    updateMonthYearDisplay();
    const today = new Date();
    
    // Get screenings from filtered movies (respects UI filters)
    const moviesToUse = filteredMovies.length > 0 ? filteredMovies : moviesData;
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
function getFilteredMoviesForDownload(minRating) {
    return moviesData.filter(movie => {
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

        // Director filter
        if (selectedDirector && movie.director !== selectedDirector) {
            return false;
        }

        // Search filter
        if (searchTerm) {
            const haystack = (movie.description || '').toLowerCase();
            if (!haystack.includes(searchTerm)) {
                return false;
            }
        }

        // Date range filter
        if (dateRangeStart && dateRangeEnd) {
            const hasScreeningInRange = movie.screenings.some(screening => {
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
    const filteredMovies = getFilteredMoviesForDownload(minRating);
    
    if (filteredMovies.length === 0) {
        alert('No events match the selected filters.');
        return;
    }
    
    // Convert aggregated movies back to individual screenings for ICS
    const screenings = [];
    filteredMovies.forEach(movie => {
        if (Array.isArray(movie.screenings)) {
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
    
    movies.forEach(movie => {
        const startDateTime = formatDateTimeForICS(movie.date, movie.time);
        const endDateTime = formatDateTimeForICS(movie.date, movie.time, 2); // 2 hour duration
        
        icsContent += [
            'BEGIN:VEVENT',
            `UID:${movie.id}@culturecalendar.local`,
            `DTSTAMP:${timestamp}`,
            `DTSTART;${startDateTime}`,
            `DTEND;${endDateTime}`,
            `SUMMARY:★${movie.rating}/10 - ${movie.title}`,
            `DESCRIPTION:${formatDescriptionForICS(movie.description)}`,
            `LOCATION:Austin Film Society Cinema, 6226 Middle Fiskville Rd, Austin, TX 78752`,
            `URL:${movie.url || 'https://www.austinfilm.org/'}`,
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
        'AlienatedMajesty': 'Alienated Majesty Books',
        'FirstLight': 'First Light Austin'
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
        'AlienatedMajesty': 'AMB',
        'FirstLight': 'FLA'
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
    return new Date(parts[0], parts[1] - 1, parts[2]);
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
    const classicalEvents = moviesData.filter(event => 
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