"""
Transcript text analysis: keyword highlighting, sentiment, readability.
"""

from __future__ import annotations

import re
from typing import Optional


def highlight_keywords(text: str, keywords: list[str]) -> str:
    """
    Highlight keywords in transcript text.
    
    Args:
        text: Transcript text
        keywords: List of keywords to highlight
    
    Returns:
        HTML text with highlighted keywords
    """
    highlighted = text
    
    for keyword in keywords:
        # Case-insensitive replacement
        pattern = re.compile(re.escape(keyword), re.IGNORECASE)
        highlighted = pattern.sub(
            lambda m: f'<mark style="background-color: yellow;">{m.group()}</mark>',
            highlighted
        )
    
    return highlighted


def extract_legal_citations_from_transcript(text: str) -> list[str]:
    """
    Extract legal citations mentioned in oral argument.
    
    Args:
        text: Transcript text
    
    Returns:
        List of citations
    """
    citations = []
    
    # NH Reporter citations
    nh_pattern = r"\b(\d+)\s+N\.?H\.?\s+(\d+)\b"
    citations.extend(re.findall(nh_pattern, text))
    
    # Neutral citations
    neutral_pattern = r"\b(20\d{2})[\s\-]NH[\s\-](\d+)\b"
    citations.extend(re.findall(neutral_pattern, text))
    
    # RSA citations
    rsa_pattern = r"\bRSA\s+(\d+[:\-][A-Z\d\-:]+)\b"
    citations.extend(re.findall(rsa_pattern, text))
    
    return [" ".join(c) if isinstance(c, tuple) else c for c in citations]


def calculate_readability_score(text: str) -> dict:
    """
    Calculate readability metrics for transcript.
    
    Uses Flesch Reading Ease and other metrics.
    
    Args:
        text: Transcript text
    
    Returns:
        Dict with readability metrics
    """
    # Count sentences
    sentences = re.split(r'[.!?]+', text)
    sentences = [s for s in sentences if s.strip()]
    sentence_count = len(sentences)
    
    # Count words
    words = text.split()
    word_count = len(words)
    
    # Count syllables (rough approximation)
    syllable_count = sum(count_syllables(word) for word in words)
    
    if sentence_count == 0 or word_count == 0:
        return {
            "flesch_reading_ease": 0,
            "avg_words_per_sentence": 0,
            "avg_syllables_per_word": 0,
        }
    
    # Flesch Reading Ease
    # FRE = 206.835 - 1.015 * (words/sentences) - 84.6 * (syllables/words)
    words_per_sentence = word_count / sentence_count
    syllables_per_word = syllable_count / word_count
    
    fre = 206.835 - (1.015 * words_per_sentence) - (84.6 * syllables_per_word)
    
    return {
        "flesch_reading_ease": max(0, min(100, fre)),
        "avg_words_per_sentence": words_per_sentence,
        "avg_syllables_per_word": syllables_per_word,
        "word_count": word_count,
        "sentence_count": sentence_count,
    }


def count_syllables(word: str) -> int:
    """
    Count syllables in a word (rough approximation).
    
    Args:
        word: Word to count syllables in
    
    Returns:
        Syllable count
    """
    word = word.lower()
    vowels = "aeiouy"
    syllable_count = 0
    previous_was_vowel = False
    
    for char in word:
        is_vowel = char in vowels
        if is_vowel and not previous_was_vowel:
            syllable_count += 1
        previous_was_vowel = is_vowel
    
    # Adjust for silent e
    if word.endswith("e"):
        syllable_count -= 1
    
    # At least 1 syllable
    if syllable_count == 0:
        syllable_count = 1
    
    return syllable_count


def extract_frequently_discussed_topics(text: str, top_n: int = 10) -> list[tuple[str, int]]:
    """
    Extract frequently discussed topics/words from transcript.
    
    Args:
        text: Transcript text
        top_n: Number of top topics to return
    
    Returns:
        List of (word, count) tuples
    """
    # Remove common stopwords
    stopwords = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "up", "about", "into", "through", "during",
        "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
        "do", "does", "did", "will", "would", "could", "should", "may", "might",
        "i", "you", "he", "she", "it", "we", "they", "this", "that", "these", "those",
        "yes", "no", "not", "just", "mr", "ms", "justice", "chief",
    }
    
    # Tokenize and count
    words = re.findall(r'\b[a-z]{4,}\b', text.lower())
    word_counts = {}
    
    for word in words:
        if word not in stopwords:
            word_counts[word] = word_counts.get(word, 0) + 1
    
    # Sort by frequency
    sorted_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)
    
    return sorted_words[:top_n]


def identify_key_exchanges(transcript: dict, min_turns: int = 5) -> list[dict]:
    """
    Identify key exchanges (rapid back-and-forth between justice and counsel).
    
    Args:
        transcript: Transcript dict with turns
        min_turns: Minimum consecutive turns to qualify as key exchange
    
    Returns:
        List of key exchange dicts
    """
    turns = transcript.get("turns", [])
    key_exchanges = []
    
    i = 0
    while i < len(turns) - min_turns:
        # Check for rapid back-and-forth
        current_speaker = turns[i].get("speaker", "")
        next_speaker = turns[i + 1].get("speaker", "") if i + 1 < len(turns) else ""
        
        if current_speaker and next_speaker and current_speaker != next_speaker:
            # Count consecutive alternating turns
            exchange_turns = [turns[i]]
            j = i + 1
            
            while j < len(turns):
                turn_speaker = turns[j].get("speaker", "")
                prev_speaker = turns[j - 1].get("speaker", "")
                
                if turn_speaker != prev_speaker and turn_speaker in [current_speaker, next_speaker]:
                    exchange_turns.append(turns[j])
                    j += 1
                else:
                    break
            
            if len(exchange_turns) >= min_turns:
                key_exchanges.append({
                    "start_index": i,
                    "turn_count": len(exchange_turns),
                    "speakers": [current_speaker, next_speaker],
                    "turns": exchange_turns,
                })
                i = j
            else:
                i += 1
        else:
            i += 1
    
    return key_exchanges
