# This module has been split into:
#   app.domain.scoring   — MatchedOffer, MatchScore, ScoreComponent, OfferScorer
#   app.domain.filters   — MatchCriteria, OfferBrowseFilters, OfferFilter, FilterChain, predicate functions
#   app.domain.sorting   — SortBy, MatchSortBy, SortOrder, sort_offers, sort_matched_offers
#   app.domain.salary_calculator — monthly_gross_amount, representative_monthly_salary
#
# Re-exported here for backward compatibility only.

from app.domain.filters import (  # noqa: F401
    FilterChain,
    MatchCriteria,
    OfferBrowseFilters,
    OfferFilter,
    expired_matches,
    level_matches,
    location_matches,
    salary_meets_minimum,
    tech_stack_matches,
    text_matches,
)
from app.domain.salary_calculator import (  # noqa: F401
    monthly_gross_amount,
    representative_monthly_salary,
)
from app.domain.scoring import (  # noqa: F401
    MatchedOffer,
    MatchScore,
    OfferScorer,
    ScoreComponent,
)
from app.domain.sorting import (  # noqa: F401
    MatchSortBy,
    SortBy,
    SortOrder,
    offer_sort_key,
    sort_matched_offers,
    sort_offers,
)
