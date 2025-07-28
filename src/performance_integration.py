"""
Performance Integration Module
Seamless integration of parallel architecture into existing codebase
"""

from typing import Dict, List, Optional, Callable
import time
from datetime import datetime

from .parallel_scraper import ParallelMultiVenueScraper, create_scraper


class PerformanceMonitor:
    """Monitor and track scraping performance metrics"""
    
    def __init__(self):
        self.metrics = {
            "total_runs": 0,
            "avg_time": 0.0,
            "avg_events": 0,
            "last_run": None,
            "best_time": float('inf'),
            "venue_performance": {}
        }
    
    def track_run(self, events_count: int, execution_time: float, venue_results: Dict = None):
        """Track performance metrics for a scraping run"""
        self.metrics["total_runs"] += 1
        
        # Update averages
        prev_avg_time = self.metrics["avg_time"]
        prev_avg_events = self.metrics["avg_events"]
        
        self.metrics["avg_time"] = (
            (prev_avg_time * (self.metrics["total_runs"] - 1) + execution_time) 
            / self.metrics["total_runs"]
        )
        
        self.metrics["avg_events"] = (
            (prev_avg_events * (self.metrics["total_runs"] - 1) + events_count) 
            / self.metrics["total_runs"]
        )
        
        # Update best time
        if execution_time < self.metrics["best_time"]:
            self.metrics["best_time"] = execution_time
        
        # Update last run info
        self.metrics["last_run"] = {
            "timestamp": datetime.now().isoformat(),
            "events": events_count,
            "time": execution_time,
            "venue_results": venue_results
        }
        
        # Track venue-specific performance
        if venue_results:
            for venue, result in venue_results.items():
                if venue not in self.metrics["venue_performance"]:
                    self.metrics["venue_performance"][venue] = {
                        "total_runs": 0,
                        "avg_events": 0,
                        "success_rate": 0.0
                    }
                
                venue_metrics = self.metrics["venue_performance"][venue]
                venue_metrics["total_runs"] += 1
                
                if result.get("status") == "success":
                    events = len(result.get("events", []))
                    prev_avg = venue_metrics["avg_events"]
                    venue_metrics["avg_events"] = (
                        (prev_avg * (venue_metrics["total_runs"] - 1) + events) 
                        / venue_metrics["total_runs"]
                    )
    
    def get_performance_report(self) -> Dict:
        """Get comprehensive performance report"""
        return {
            "summary": {
                "total_runs": self.metrics["total_runs"],
                "average_time": round(self.metrics["avg_time"], 2),
                "average_events": round(self.metrics["avg_events"], 1),
                "best_time": round(self.metrics["best_time"], 2) if self.metrics["best_time"] != float('inf') else None,
                "last_run": self.metrics["last_run"]
            },
            "venue_performance": self.metrics["venue_performance"],
            "recommendations": self._generate_recommendations()
        }
    
    def _generate_recommendations(self) -> List[str]:
        """Generate performance optimization recommendations"""
        recommendations = []
        
        if self.metrics["total_runs"] == 0:
            return ["No performance data available yet"]
        
        # Time-based recommendations
        if self.metrics["avg_time"] > 30:
            recommendations.append("Consider increasing max_workers for faster execution")
        elif self.metrics["avg_time"] < 10:
            recommendations.append("Excellent performance! Current configuration is optimal")
        
        # Venue-specific recommendations
        failing_venues = []
        for venue, metrics in self.metrics["venue_performance"].items():
            if metrics["avg_events"] == 0:
                failing_venues.append(venue)
        
        if failing_venues:
            recommendations.append(f"Check scrapers for: {', '.join(failing_venues)}")
        
        return recommendations


class SmartScraperFactory:
    """Factory for creating optimally configured scrapers"""
    
    @staticmethod
    def create_optimal_scraper(
        performance_profile: str = "balanced",
        custom_config: Dict = None
    ) -> ParallelMultiVenueScraper:
        """
        Create optimally configured scraper based on performance profile
        
        Args:
            performance_profile: "conservative", "balanced", "aggressive", or "custom"
            custom_config: Custom configuration for "custom" profile
        
        Returns:
            Configured ParallelMultiVenueScraper instance
        """
        configs = {
            "conservative": {"max_workers": 4, "timeout": 45},
            "balanced": {"max_workers": 8, "timeout": 30},
            "aggressive": {"max_workers": 12, "timeout": 20},
        }
        
        if performance_profile == "custom" and custom_config:
            config = custom_config
        else:
            config = configs.get(performance_profile, configs["balanced"])
        
        return ParallelMultiVenueScraper(
            max_workers=config["max_workers"],
            timeout_per_venue=config["timeout"]
        )
    
    @staticmethod
    def auto_configure(venue_count: int = 11) -> Dict:
        """
        Automatically configure based on system and venue count
        
        Args:
            venue_count: Number of venues to scrape
        
        Returns:
            Optimal configuration dictionary
        """
        import os
        
        # Estimate based on CPU cores
        cpu_cores = os.cpu_count() or 4
        
        # Conservative approach: don't exceed CPU cores + 4
        max_workers = min(venue_count, cpu_cores + 4)
        
        # Adjust timeout based on worker count
        if max_workers >= 8:
            timeout = 25  # Aggressive
        elif max_workers >= 6:
            timeout = 30  # Balanced
        else:
            timeout = 40  # Conservative
        
        return {
            "max_workers": max_workers,
            "timeout": timeout,
            "profile": "auto-configured"
        }


def progress_printer(venue_name: str, status: str, percentage: int):
    """Default progress printer for parallel scraping"""
    print(f"📊 {venue_name}: {status} ({percentage}% complete)")


def enhanced_scrape_with_monitoring(
    target_week: bool = False,
    days_ahead: int = None,
    performance_profile: str = "balanced",
    show_progress: bool = True,
    monitor: PerformanceMonitor = None
) -> tuple:
    """
    Enhanced scraping function with built-in performance monitoring
    
    Args:
        target_week: Filter to current week
        days_ahead: Days ahead to scrape
        performance_profile: Performance profile ("conservative", "balanced", "aggressive")
        show_progress: Show progress during scraping
        monitor: Optional performance monitor instance
    
    Returns:
        Tuple of (events, execution_time, performance_report)
    """
    # Create optimally configured scraper
    scraper = SmartScraperFactory.create_optimal_scraper(performance_profile)
    
    # Initialize monitor if not provided
    if monitor is None:
        monitor = PerformanceMonitor()
    
    # Progress callback
    progress_callback = progress_printer if show_progress else None
    
    print(f"🚀 Starting enhanced scraping (profile: {performance_profile})...")
    start_time = time.time()
    
    try:
        # Execute parallel scraping
        events = scraper.scrape_all_venues_parallel(
            target_week=target_week,
            days_ahead=days_ahead,
            progress_callback=progress_callback
        )
        
        execution_time = time.time() - start_time
        
        # Get performance metrics
        performance_metrics = scraper.get_performance_metrics()
        
        # Track in monitor
        monitor.track_run(
            events_count=len(events),
            execution_time=execution_time,
            venue_results=performance_metrics.get("progress", {})
        )
        
        # Generate report
        performance_report = monitor.get_performance_report()
        
        print(f"✅ Enhanced scraping completed: {len(events)} events in {execution_time:.2f}s")
        
        return events, execution_time, performance_report
        
    except Exception as e:
        execution_time = time.time() - start_time
        print(f"❌ Enhanced scraping failed after {execution_time:.2f}s: {e}")
        
        # Track failed run
        monitor.track_run(0, execution_time)
        
        raise


# Global performance monitor instance
global_monitor = PerformanceMonitor()


def quick_parallel_scrape(target_week: bool = False) -> List[Dict]:
    """
    Quick parallel scraping function for easy integration
    
    Args:
        target_week: Filter to current week
    
    Returns:
        List of events
    """
    events, _, _ = enhanced_scrape_with_monitoring(
        target_week=target_week,
        performance_profile="balanced",
        show_progress=False,
        monitor=global_monitor
    )
    return events


def get_global_performance_stats() -> Dict:
    """Get global performance statistics"""
    return global_monitor.get_performance_report()


# Compatibility functions for easy migration
def migrate_from_sequential(existing_scraper_code: str) -> str:
    """
    Help migrate existing sequential scraper code to parallel
    
    Args:
        existing_scraper_code: String containing existing scraper code
    
    Returns:
        Suggested parallel code
    """
    suggestions = []
    
    if "MultiVenueScraper()" in existing_scraper_code:
        suggestions.append(
            "Replace 'MultiVenueScraper()' with 'MultiVenueScraper()' (parallel is now default!)"
        )
    
    if "scrape_all_venues(" in existing_scraper_code:
        suggestions.append(
            "No changes needed! scrape_all_venues() now uses parallel processing automatically"
        )
    
    if "scrape_new_events_only(" in existing_scraper_code:
        suggestions.append(
            "No changes needed! scrape_new_events_only() now uses parallel processing automatically"
        )
    
    if len(suggestions) == 0:
        suggestions.append("Your code should work without changes - parallel is now the default!")
    
    return "\n".join([f"✅ {suggestion}" for suggestion in suggestions])