import re
import asyncio
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from difflib import SequenceMatcher
from pydantic import BaseModel, Field

from core.models import SportsbookOdds

logger = logging.getLogger("SpreadCore.Matcher")


class RawSportsbookEvent(BaseModel):
    """Raw event payload received from a sportsbook scraper/API."""
    bookmaker: str
    category: str  # e.g., "Football", "Basketball"
    home_team: str
    away_team: str
    odds_home: float
    odds_away: float
    start_time: datetime


class Normalizer:
    """Helper class to clean and normalize strings for entity matching."""

    STOP_WORDS = {"fc", "cf", "club", "united", "city", "vs", "v", "-", "sports"}

    @classmethod
    def clean_name(cls, name: str) -> str:
        """Removes punctuation, extra spaces, and common sports suffixes."""
        name = name.lower()
        name = re.sub(r"[^\w\s]", "", name)
        words = [w for w in name.split() if w not in cls.STOP_WORDS]
        return " ".join(words)


class FuzzyEventMatcher:
    """Matches team names and events across different platforms using similarity scoring."""

    def __init__(self, similarity_threshold: float = 0.80):
        self.similarity_threshold = similarity_threshold
        # Cache for mapped canonical IDs -> (home_team, away_team)
        self.canonical_events: Dict[str, Tuple[str, str]] = {}

    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """Calculates string similarity ratio using SequenceMatcher."""
        clean1 = Normalizer.clean_name(str1)
        clean2 = Normalizer.clean_name(str2)
        return SequenceMatcher(None, clean1, clean2).ratio()

    def match_teams(self, poly_home: str, poly_away: str, book_home: str, book_away: str) -> bool:
        """
        Evaluates if two sets of team names represent the same match.
        Checks both direct match (Home vs Home) and reversed match (if teams are inverted).
        """
        home_sim = self._calculate_similarity(poly_home, book_home)
        away_sim = self._calculate_similarity(poly_away, book_away)

        direct_score = (home_sim + away_sim) / 2.0

        if direct_score >= self.similarity_threshold:
            return True

        # Check for inverted order
        inv_home_sim = self._calculate_similarity(poly_home, book_away)
        inv_away_sim = self._calculate_similarity(poly_away, book_home)
        inverted_score = (inv_home_sim + inv_away_sim) / 2.0

        return inverted_score >= self.similarity_threshold

    def get_or_create_mapping_id(self, home_team: str, away_team: str) -> str:
        """
        Finds an existing canonical mapping_id or generates a new standardized one.
        """
        clean_home = Normalizer.clean_name(home_team)
        clean_away = Normalizer.clean_name(away_team)

        for mapping_id, (c_home, c_away) in self.canonical_events.items():
            if self.match_teams(c_home, c_away, home_team, away_team):
                return mapping_id

        # Create new canonical ID
        canonical_id = f"match_{clean_home.replace(' ', '_')}_vs_{clean_away.replace(' ', '_')}"
        self.canonical_events[canonical_id] = (home_team, away_team)
        logger.info(f"[EVENT MATCHER] Created new event mapping: {canonical_id} ('{home_team}' vs '{away_team}')")
        return canonical_id


class SportsbookFeedAdapter:
    """Adapter for ingesting and processing external sportsbook feeds."""

    def __init__(self, matcher: FuzzyEventMatcher):
        self.matcher = matcher

    def parse_and_map(self, raw_event: RawSportsbookEvent) -> Tuple[str, List[SportsbookOdds]]:
        """
        Maps a raw sportsbook event to a canonical ID and converts odds to standard format.
        """
        mapping_id = self.matcher.get_or_create_mapping_id(raw_event.home_team, raw_event.away_team)

        odds_home = SportsbookOdds(
            bookmaker_name=raw_event.bookmaker,
            event_id=mapping_id,
            outcome_name=raw_event.home_team,
            odds=raw_event.odds_home
        )

        odds_away = SportsbookOdds(
            bookmaker_name=raw_event.bookmaker,
            event_id=mapping_id,
            outcome_name=raw_event.away_team,
            odds=raw_event.odds_away
        )

        return mapping_id, [odds_home, odds_away]
