# Culture Calendar Design System

## Overview
A sophisticated, newspaper-inspired design system using ET Book typography and New York Times aesthetic principles.

## Typography

### Primary Font Stack
- **Serif (Primary)**: ET Book, Bembo, Georgia, serif
- **Sans-serif (UI)**: Libre Franklin, Franklin Gothic, Helvetica Neue, sans-serif

### Scale
- **Display**: 48px/56px (Masthead)
- **H1**: 32px/40px (Section headers)
- **H2**: 24px/32px (Event titles)
- **H3**: 20px/28px (Subsections)
- **Body**: 17px/26px (Main text)
- **Small**: 14px/20px (Metadata)
- **Micro**: 12px/16px (Navigation, captions)

## Color Palette

### Core Colors
- **Primary Black**: #000000
- **Text Black**: #212121
- **Dark Gray**: #333333
- **Medium Gray**: #666666
- **Light Gray**: #999999
- **Background White**: #ffffff
- **Subtle Background**: #fafafa

### Accent Colors
- **Link Blue**: #326891
- **Visited Blue**: #1a5490
- **Border Gray**: #e6e6e6

### Semantic Colors
- **Warning Background**: #fff3cd
- **Warning Border**: #f39c12
- **Warning Text**: #856404

## Layout

### Grid System
- **Max Width**: 1200px
- **Desktop**: 12-column grid
- **Tablet**: 6-column grid (768px breakpoint)
- **Mobile**: Single column (480px breakpoint)
- **Gutters**: 24px
- **Margins**: 48px desktop, 24px tablet, 16px mobile

### Reading Column
- **Optimal Width**: 840px (65-75 characters)
- **Line Height**: 1.529 (26px)

## Components

### Masthead
- **Height**: Variable based on content
- **Top Border**: 3px solid black
- **Bottom Border**: 4px solid black with 1px accent line
- **Typography**: ET Book, center-aligned

### Navigation
- **Height**: 48px
- **Typography**: 12px uppercase, letter-spacing 0.1em
- **Sticky**: Top of viewport
- **Separators**: 1px vertical lines

### Event Cards
- **Article Style**: Bottom border dividers
- **Hover**: Subtle background change (#fafafa)
- **Typography**: ET Book for titles, Franklin Gothic for metadata
- **Spacing**: 32px between cards

### Filter Sidebar
- **Width**: 400px desktop, 100% mobile
- **Position**: Fixed right
- **Background**: #fafafa
- **Animation**: 300ms ease slide-in

### Footer
- **Background**: #fafafa
- **Grid**: 5-column layout (2fr 1fr 1fr 1fr 1fr)
- **Typography**: Mixed serif/sans-serif hierarchy

## Interactive States

### Links
- **Default**: #326891, no underline
- **Hover**: Underline appears, 2px offset
- **Visited**: #1a5490

### Buttons
- **Default**: Transparent background, 1px black border
- **Hover**: Black background, white text
- **Typography**: 14px Franklin Gothic, uppercase

### Form Elements
- **Focus**: 2px black border
- **Typography**: ET Book for inputs
- **Background**: White

## Accessibility

### Contrast Ratios
- **AAA Compliant**: All text meets WCAG 2.1 AAA standards
- **Focus Indicators**: Clear 2px borders on all interactive elements
- **Touch Targets**: Minimum 44px for mobile interactions

### Typography
- **Font Size**: Minimum 14px for body text
- **Line Height**: 1.5+ for readability
- **Letter Spacing**: Optimized for screen reading

## Responsive Breakpoints

### Mobile (max-width: 768px)
- **Masthead**: Reduced font sizes
- **Navigation**: Wrapped layout, removed separators
- **Sidebar**: Full-width overlay
- **Footer**: Single-column stack
- **Calendar**: Reduced cell size

### Print Styles
- **Font Size**: 11pt base
- **Colors**: Black and white only
- **Hidden Elements**: Navigation, sidebar, interactive buttons
- **Page Breaks**: Avoid breaking event cards

## Animation & Transitions

### Standard Duration
- **Quick**: 200ms (hover states)
- **Standard**: 300ms (sidebar, modals)
- **Slow**: 500ms (page transitions)

### Easing
- **Default**: ease
- **Bounce**: cubic-bezier(0.68, -0.55, 0.265, 1.55)

## Implementation Notes

### Font Loading
- **ET Book**: Loaded from CDN (Edward Tufte's repository)
- **Libre Franklin**: Google Fonts fallback
- **Fallbacks**: System fonts for reliability

### Browser Support
- **Modern Browsers**: Full feature support
- **Legacy Support**: Graceful degradation
- **Mobile First**: Progressive enhancement approach

### Performance
- **Critical CSS**: Inline for above-fold content
- **Font Display**: swap for web fonts
- **Image Optimization**: WebP with fallbacks

## Design Principles

### Editorial Excellence
- **Hierarchy**: Size and weight over color
- **Whitespace**: Generous margins and padding
- **Typography**: Content-first approach

### Newspaper Tradition
- **Datelines**: Uppercase, small caps styling
- **Bylines**: Italic, attributed content
- **Columns**: Narrow reading widths
- **Borders**: Hairline rules and dividers

### Modern Web Standards
- **Semantic HTML**: Article, section, nav tags
- **Accessibility**: ARIA labels, focus management
- **Performance**: Optimized assets, lazy loading
- **Progressive Enhancement**: Core functionality without JavaScript

This design system creates a timeless, sophisticated experience that honors both newspaper tradition and modern web standards while maintaining excellent readability and usability across all devices.