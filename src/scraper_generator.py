"""
Scraper generator system - Auto-generate scrapers from venue schemas
"""

import os
from typing import Dict, List
from .schemas import SchemaRegistry, get_venue_schema, VENUE_SCHEMAS


class ScraperGenerator:
    """Generate scraper boilerplate code from venue schemas"""
    
    def __init__(self):
        self.template_dir = "src/scraper_templates"
        
    def generate_scraper(self, venue_name: str, venue_config: Dict) -> str:
        """
        Generate a scraper class from venue configuration
        
        Args:
            venue_name: Name of the venue (e.g., "NewVenue")
            venue_config: Configuration dict with:
                - venue_type: Type of venue (film, concert, book_club, etc.)
                - base_url: Base URL for the venue
                - target_urls: List of URLs to scrape
                - venue_description: Human-readable description
                
        Returns:
            Generated Python code as string
        """
        venue_type = venue_config.get('venue_type', 'generic')
        schema = get_venue_schema(venue_name) if venue_name in VENUE_SCHEMAS else SchemaRegistry.get_schema(venue_type)
        
        # Generate the scraper code
        code = self._generate_scraper_code(venue_name, venue_config, schema)
        
        return code
    
    def _generate_scraper_code(self, venue_name: str, config: Dict, schema: Dict) -> str:
        """Generate the actual scraper code"""
        
        base_url = config.get('base_url', '')
        target_urls = config.get('target_urls', [])
        venue_description = config.get('venue_description', f'{venue_name} events')
        venue_type = config.get('venue_type', 'generic')
        
        # Build schema fields for the data schema method
        schema_fields = self._build_schema_fields(schema)
        
        # Build extraction hints for LLM prompts
        extraction_hints = self._build_extraction_hints(schema)
        
        # Build the class template
        class_template = f'''"""
{venue_description} scraper using LLM-powered architecture
Auto-generated from schema on {self._get_timestamp()}
"""

from typing import Dict, List
from src.base_scraper import BaseScraper


class {venue_name}Scraper(BaseScraper):
    """Simple scraper for {venue_name} events - LLM-powered extraction"""
    
    def __init__(self):
        super().__init__(
            base_url="{base_url}",
            venue_name="{venue_name}"
        )
    
    def get_target_urls(self) -> List[str]:
        """Return URLs to scrape for events"""
        return {target_urls}
    
    def get_data_schema(self) -> Dict:
        """Return the expected data schema for {venue_type} events"""
        return {{
{schema_fields}
        }}
    
    def get_fallback_data(self) -> List[Dict]:
        """Return empty list - we only want real data"""
        return []
'''
        
        template = class_template

        return template
    
    def _build_schema_fields(self, schema: Dict) -> str:
        """Build the schema fields string for the generated code"""
        lines = []
        for field_name, field_def in schema.items():
            field_type = field_def.get('type', 'string')
            required = field_def.get('required', False)
            description = field_def.get('description', '')
            
            lines.append(f"            '{field_name}': {{'type': '{field_type}', 'required': {required}, 'description': '{description}'}},")
        
        return "\\n".join(lines)
    
    def _build_extraction_hints(self, schema: Dict) -> str:
        """Build extraction hints for LLM prompts"""
        hints = []
        for field_name, field_def in schema.items():
            extraction_hints = field_def.get('extraction_hints', [])
            if extraction_hints:
                hints.append(f"- {field_name}: Look for {', '.join(extraction_hints)}")
            else:
                hints.append(f"- {field_name}: {field_def.get('description', '')}")
        
        return "\\n".join(hints)
    
    def _get_timestamp(self) -> str:
        """Get current timestamp for code generation"""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def save_scraper(self, venue_name: str, venue_config: Dict, output_path: str = None) -> str:
        """
        Generate and save a scraper to file
        
        Returns:
            Path to the saved file
        """
        if not output_path:
            output_path = f"src/scrapers/{venue_name.lower()}_scraper.py"
        
        code = self.generate_scraper(venue_name, venue_config)
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        with open(output_path, 'w') as f:
            f.write(code)
        
        print(f"Generated scraper saved to: {output_path}")
        return output_path
    
    def generate_venue_config_template(self, venue_type: str) -> Dict:
        """Generate a configuration template for a new venue"""
        templates = {
            'film': {
                'venue_type': 'film',
                'base_url': 'https://example-cinema.com',
                'target_urls': ['https://example-cinema.com/calendar', 'https://example-cinema.com/events'],
                'venue_description': 'Independent cinema screening arthouse films',
                'example_venue_name': 'ExampleCinema'
            },
            'book_club': {
                'venue_type': 'book_club',
                'base_url': 'https://example-bookstore.com',
                'target_urls': ['https://example-bookstore.com/book-clubs', 'https://example-bookstore.com/events'],
                'venue_description': 'Independent bookstore hosting book clubs',
                'example_venue_name': 'ExampleBooks'
            },
            'concert': {
                'venue_type': 'concert',
                'base_url': 'https://example-orchestra.org',
                'target_urls': ['https://example-orchestra.org/concerts', 'https://example-orchestra.org/season'],
                'venue_description': 'Classical music ensemble performances',
                'example_venue_name': 'ExampleOrchestra'
            },
            'theater': {
                'venue_type': 'theater',
                'base_url': 'https://example-theater.org',
                'target_urls': ['https://example-theater.org/shows', 'https://example-theater.org/season'],
                'venue_description': 'Live theater productions',
                'example_venue_name': 'ExampleTheater'
            }
        }
        
        return templates.get(venue_type, {
            'venue_type': venue_type,
            'base_url': 'https://example-venue.com',
            'target_urls': ['https://example-venue.com/events'],
            'venue_description': f'{venue_type.title()} venue',
            'example_venue_name': 'ExampleVenue'
        })


def create_new_venue_scraper(venue_name: str, venue_type: str, **config_overrides):
    """
    Convenience function to create a new venue scraper
    
    Args:
        venue_name: Name of the venue (e.g., "NewCinema")
        venue_type: Type of venue (film, concert, book_club, theater)
        **config_overrides: Override default config values
        
    Returns:
        Path to generated scraper file
    """
    generator = ScraperGenerator()
    
    # Get template config and override with provided values
    config = generator.generate_venue_config_template(venue_type)
    config.update(config_overrides)
    
    # Generate and save the scraper
    output_path = generator.save_scraper(venue_name, config)
    
    print(f"\\n🎉 Generated {venue_name}Scraper!")
    print(f"📁 File: {output_path}")
    print(f"🏗️  Venue type: {venue_type}")
    print(f"🌐 Base URL: {config.get('base_url')}")
    print(f"\\n📝 Next steps:")
    print(f"   1. Edit {output_path} to customize URLs and extraction logic")
    print(f"   2. Add {venue_name}Scraper to src/scrapers/__init__.py")
    print(f"   3. Update VENUE_SCHEMAS in src/schemas.py")
    print(f"   4. Test with: python -c 'from src.scrapers import {venue_name}Scraper; s = {venue_name}Scraper(); print(s.scrape_events())'")
    
    return output_path


if __name__ == "__main__":
    # Example usage
    print("🏗️  Scraper Generator Demo")
    print("="*40)
    
    # Show available venue types
    print("Available venue types:")
    for venue_type in SchemaRegistry.get_available_types():
        print(f"  - {venue_type}")
    
    print("\\n💡 To create a new scraper:")
    print("   from src.scraper_generator import create_new_venue_scraper")
    print("   create_new_venue_scraper('NewCinema', 'film', base_url='https://newcinema.com')")