# Product Requirement Document: Culture Calendar

## 1. Introduction & Vision

Culture Calendar is a personal automation project designed to aggregate cultural events from various online sources, enrich them with personalized ratings and external data, and consolidate them into a single, easily accessible Google Calendar. The vision is to create a smart, curated, and effortless way to keep track of interesting cultural happenings, starting with film screenings and expanding to other areas like bookstore events and classical music concerts.

## 2. Problem Statement

Manually tracking cultural events across multiple websites is time-consuming and inefficient. It's difficult to get a consolidated view of what's happening, and it requires extra effort to research each event to determine if it's a good fit for one's personal tastes. This often leads to missed opportunities and a reactive, rather than proactive, approach to planning cultural outings.

## 3. Goals & Objectives

*   **Automate Event Aggregation:** Eliminate the need to manually check multiple websites for event information.
*   **Centralize Event Information:** Provide a single source of truth for all tracked cultural events in a familiar format (Google Calendar).
*   **Personalize & Curate:** Automatically enrich events with ratings and relevant details to make it easier to decide what to attend.
*   **Create a Scalable System:** Build a foundation that can be easily expanded to include new event sources and types in the future.

## 4. Target Audience

The primary user is the project owner, an individual with a keen interest in cultural events who wants a more efficient and personalized way to manage their cultural life.

## 5. Project Phases & Features

### Phase 1: MVP - Austin Film Society Integration

The Minimum Viable Product will focus on a single source to prove the core concept.

#### Core Features

**1. Scheduled Web Scraping:**
    - The system will automatically fetch event data from the Austin Film Society (AFS) calendar on a predefined schedule (e.g., daily, weekly).
    - **Source URL:** `https://www.austinfilm.org/calendar/`

**2. Content Processing & Enrichment:**
    - **Page Processing:** Use the Firecrawl API to process the AFS calendar page and extract event listings.
    - **Detail Extraction:** For each event, follow its link to the detail page to determine if it is a "special screening" (e.g., Q&A with the director, 35mm print).
    - **AI-Powered Rating:** Use the Perplexity AI API to research movie titles and generate a preliminary rating or summary.

**3. Personalized Rating System:**
    - A mechanism will be developed to assign a final rating to each event. This rating will be a composite of:
        - The rating/information gathered via the Perplexity API.
        - A personal preference score derived from a user-defined text file (e.g., `preferences.txt`) containing keywords, directors, genres, etc.
        - A boost for "special screenings".

**4. iCalendar (`.ics`) File Generation:**
    - The system will generate a standard `.ics` file containing all the processed and enriched events.
    - Each calendar event will include:
        - Event Title
        - Date & Time
        - Location (AFS Cinema)
        - Description (including the calculated rating, an explanation for the rating, and a note if it's a special screening).
        - A link back to the original AFS event page.
    - This file can be manually imported into Google Calendar.

### Future Phases (Roadmap)

*   **Phase 2: Source Expansion:** Add support for more websites, such as local bookstores, music venues (for classical/chamber music), and other art-house cinemas. This will require making the scraping and processing logic more generic.
*   **Phase 3: Direct Calendar Integration:** Implement direct integration with the Google Calendar API to add/update events automatically, removing the need for manual `.ics` file imports.
*   **Phase 4: UI for Management:** Develop a simple web interface to manage event sources, view aggregated events, and tweak personalization settings.

## 6. Technical Requirements

*   **Programming Language:** To be determined, but a language like Python is recommended for its strong support for scripting, web scraping, and API integrations.
*   **APIs:**
    - **Firecrawl API:** For reliable content extraction from web pages.
    - **Perplexity AI API:** For enriching event data with external information.
*   **Configuration:**
    - API keys and other sensitive information will be managed securely using a `.env` file.
*   **Scheduling:**
    - The scraping process will be run on a schedule using a `cron` job or a library-based scheduler.

## 7. Assumptions & Constraints

*   The website structure of the Austin Film Society is reasonably stable.
*   The Firecrawl and Perplexity APIs have the capabilities required for the specified extraction and enrichment tasks.
*   The user possesses valid API keys for the required services.
*   For Phase 1, the output is an `.ics` file, and manual import is an acceptable workflow. 
