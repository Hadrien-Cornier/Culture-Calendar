// Global variables
let moviesData = [];
let filteredMovies = [];

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

// Initialize the app
document.addEventListener('DOMContentLoaded', function() {
    setupEventListeners();
    loadMoviesData();
});

// Set up event listeners
function setupEventListeners() {
    ratingSlider.addEventListener('input', function() {
        ratingValue.textContent = this.value;
        updateFilteredMovies();
    });

    downloadBtn.addEventListener('click', function() {
        const minRating = parseInt(ratingSlider.value);
        downloadFilteredCalendar(minRating);
    });

    listViewBtn.addEventListener('click', function() {
        switchToListView();
    });

    calendarViewBtn.addEventListener('click', function() {
        switchToCalendarView();
    });
}

// Switch to list view
function switchToListView() {
    listView.style.display = 'block';
    calendarView.style.display = 'none';
    listViewBtn.classList.add('active');
    calendarViewBtn.classList.remove('active');
}

// Switch to calendar view
function switchToCalendarView() {
    listView.style.display = 'none';
    calendarView.style.display = 'block';
    listViewBtn.classList.remove('active');
    calendarViewBtn.classList.add('active');
    
    if (moviesData.length > 0) {
        renderCalendar();
    }
}

// Load movies data from JSON file
async function loadMoviesData() {
    try {
        const response = await fetch('data.json');
        if (!response.ok) {
            throw new Error('Failed to load movie data');
        }
        
        moviesData = await response.json();
        updateFilteredMovies();
        renderMovies();
        hideLoading();
    } catch (error) {
        console.error('Error loading movies data:', error);
        showError('Failed to load movie data. Please try again later.');
    }
}

// Update filtered movies based on current rating
function updateFilteredMovies() {
    const minRating = parseInt(ratingSlider.value);
    filteredMovies = moviesData.filter(movie => movie.rating >= minRating);
    updateDownloadButton();
}

// Update download button state
function updateDownloadButton() {
    const count = filteredMovies.length;
    if (count === 0) {
        downloadBtn.textContent = 'No movies match criteria';
        downloadBtn.disabled = true;
    } else {
        downloadBtn.textContent = `Download Calendar (${count} movies)`;
        downloadBtn.disabled = false;
    }
}

// Render movies list
function renderMovies() {
    if (moviesData.length === 0) {
        moviesList.innerHTML = '<p class="no-movies">No upcoming movies found.</p>';
        return;
    }

    moviesList.innerHTML = moviesData.map(movie => createMovieCard(movie)).join('');
    
    // Add event listeners for expand buttons
    document.querySelectorAll('.expand-button').forEach(button => {
        button.addEventListener('click', function() {
            const movieId = this.dataset.movieId;
            toggleDescription(movieId);
        });
    });
}

// Create HTML for a movie card
function createMovieCard(movie) {
    const shortDescription = truncateText(stripHtmlTags(movie.description), 200);
    const needsExpansion = stripHtmlTags(movie.description).length > shortDescription.length;
    
    // Create screening tags
    const screeningTags = movie.screenings.map(screening => {
        const formattedDate = formatDate(screening.date);
        const formattedTime = screening.time;
        return `<a href="${screening.url}" target="_blank" class="screening-tag">
            📅 ${formattedDate} • 🕐 ${formattedTime}
        </a>`;
    }).join('');
    
    return `
        <div class="movie-card">
            <div class="movie-header">
                <h3 class="movie-title">${escapeHtml(movie.title)}</h3>
                <div class="movie-rating">⭐${movie.rating}/10</div>
            </div>
            
            <div class="movie-info">
                <div class="screenings-container">
                    ${screeningTags}
                    ${movie.isSpecialScreening ? '<span class="special-screening-indicator">✨ Special</span>' : ''}
                </div>
            </div>
            
            <div class="movie-description">
                <div class="description-preview" id="preview-${movie.id}">
                    ${formatDescription(shortDescription)}
                </div>
                <div class="description-full" id="full-${movie.id}">
                    ${movie.description}
                </div>
                ${needsExpansion ? `
                    <button class="expand-button" data-movie-id="${movie.id}">
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
    const button = document.querySelector(`[data-movie-id="${movieId}"]`);
    
    if (full.classList.contains('expanded')) {
        // Collapse
        full.classList.remove('expanded');
        preview.style.display = 'block';
        button.textContent = 'Show More';
    } else {
        // Expand
        full.classList.add('expanded');
        preview.style.display = 'none';
        button.textContent = 'Show Less';
    }
}

// Render calendar view
function renderCalendar() {
    const today = new Date();
    const currentMonth = today.getMonth();
    const currentYear = today.getFullYear();
    
    // Get all screenings from movies data
    const allScreenings = [];
    moviesData.forEach(movie => {
        movie.screenings.forEach(screening => {
            allScreenings.push({
                ...screening,
                title: movie.title,
                rating: movie.rating,
                id: movie.id
            });
        });
    });
    
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
    
    // Get first day of month and number of days
    const firstDay = new Date(currentYear, currentMonth, 1);
    const lastDay = new Date(currentYear, currentMonth + 1, 0);
    const startDate = new Date(firstDay);
    startDate.setDate(startDate.getDate() - firstDay.getDay());
    
    // Generate calendar days
    for (let i = 0; i < 42; i++) {
        const currentDate = new Date(startDate);
        currentDate.setDate(startDate.getDate() + i);
        
        const dateStr = currentDate.toISOString().split('T')[0];
        const isCurrentMonth = currentDate.getMonth() === currentMonth;
        const isToday = dateStr === today.toISOString().split('T')[0];
        
        // Find screenings for this date
        const dayScreenings = allScreenings.filter(s => s.date === dateStr);
        
        let dayClass = 'calendar-day';
        if (!isCurrentMonth) dayClass += ' other-month';
        if (isToday) dayClass += ' today';
        
        let eventsHTML = '';
        dayScreenings.forEach(screening => {
            const ratingClass = screening.rating >= 8 ? 'high-rating' : 
                              screening.rating >= 6 ? 'medium-rating' : 'low-rating';
            eventsHTML += `
                <div class="calendar-event ${ratingClass}" title="${screening.title} - ${screening.time}">
                    ⭐${screening.rating} ${screening.title}
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
    calendarContainer.innerHTML = calendarHTML;
}

// Download filtered calendar
function downloadFilteredCalendar(minRating) {
    const filteredMovies = moviesData.filter(movie => movie.rating >= minRating);
    
    if (filteredMovies.length === 0) {
        alert('No movies match the selected rating criteria.');
        return;
    }
    
    // Convert aggregated movies back to individual screenings for ICS
    const screenings = [];
    filteredMovies.forEach(movie => {
        movie.screenings.forEach(screening => {
            screenings.push({
                title: movie.title,
                date: screening.date,
                time: screening.time,
                description: movie.description,
                rating: movie.rating,
                url: screening.url,
                id: `${movie.id}-${screening.date}-${screening.time.replace(/[^0-9]/g, '')}`
            });
        });
    });
    
    // Generate calendar content
    const icsContent = generateICSContent(screenings);
    
    // Create and trigger download
    const blob = new Blob([icsContent], { type: 'text/calendar;charset=utf-8' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `culture-calendar-${minRating}plus-${getCurrentDateString()}.ics`;
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
        ''
    ].join('\r\n');
    
    movies.forEach(movie => {
        const startDateTime = formatDateTimeForICS(movie.date, movie.time);
        const endDateTime = formatDateTimeForICS(movie.date, movie.time, 2); // 2 hour duration
        
        icsContent += [
            'BEGIN:VEVENT',
            `UID:${movie.id}@culturecalendar.local`,
            `DTSTAMP:${timestamp}`,
            `DTSTART:${startDateTime}`,
            `DTEND:${endDateTime}`,
            `SUMMARY:⭐${movie.rating}/10 - ${movie.title}`,
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

function formatDate(dateStr) {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', { 
        weekday: 'short', 
        month: 'short', 
        day: 'numeric' 
    });
}

function formatDateTimeForICS(dateStr, timeStr, hoursToAdd = 0) {
    const date = new Date(dateStr);
    
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
    
    // Convert to Austin timezone (UTC-6 or UTC-5)
    const utcDate = new Date(date.getTime() + (6 * 60 * 60 * 1000)); // Assume CST
    return utcDate.toISOString().replace(/[-:]/g, '').split('.')[0] + 'Z';
}

function getCurrentDateString() {
    const now = new Date();
    return now.toISOString().split('T')[0].replace(/-/g, '');
}

function hideLoading() {
    loadingElement.style.display = 'none';
}

function showError(message) {
    loadingElement.innerHTML = `<p class="error">⚠️ ${message}</p>`;
}