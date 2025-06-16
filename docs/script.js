// Global variables
let moviesData = [];
let filteredMovies = [];

// DOM elements
const ratingSlider = document.getElementById('rating-slider');
const ratingValue = document.getElementById('rating-value');
const downloadBtn = document.getElementById('download-btn');
const moviesList = document.getElementById('movies-list');
const loadingElement = document.getElementById('loading');

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
    const shortDescription = truncateText(movie.description, 200);
    const needsExpansion = movie.description.length > shortDescription.length;
    
    return `
        <div class="movie-card">
            <div class="movie-header">
                <h3 class="movie-title">${escapeHtml(movie.title)}</h3>
                <div class="movie-rating">⭐${movie.rating}/10</div>
            </div>
            
            <div class="movie-info">
                <span class="movie-date">📅 ${formatDate(movie.date)}</span>
                <span class="movie-time">🕐 ${movie.time}</span>
                ${movie.isSpecialScreening ? '<span class="special-screening">✨ Special Screening</span>' : ''}
            </div>
            
            <div class="movie-description">
                <div class="description-preview" id="preview-${movie.id}">
                    ${formatDescription(shortDescription)}
                </div>
                <div class="description-full" id="full-${movie.id}">
                    ${formatDescription(movie.description)}
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

// Download filtered calendar
function downloadFilteredCalendar(minRating) {
    const filteredMovies = moviesData.filter(movie => movie.rating >= minRating);
    
    if (filteredMovies.length === 0) {
        alert('No movies match the selected rating criteria.');
        return;
    }
    
    // Generate calendar content
    const icsContent = generateICSContent(filteredMovies);
    
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
    // Convert line breaks to HTML and handle basic formatting
    return text.replace(/\n/g, '<br>').replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
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