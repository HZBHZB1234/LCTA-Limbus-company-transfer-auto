"""translateFunc.matcher — AC automaton matching and proper noun analysis."""
from translateFunc.matcher.ac_automaton import AcAutomaton, ACPattern
from translateFunc.matcher.engine import MatcherEngine, MatchResult
from translateFunc.matcher.proper import ProperAnalyzer, ProperTerm

__all__ = [
    "AcAutomaton", "ACPattern",
    "MatcherEngine", "MatchResult",
    "ProperAnalyzer", "ProperTerm",
]
