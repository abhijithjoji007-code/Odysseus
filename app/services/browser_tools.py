from __future__ import annotations

import urllib.parse
import webbrowser


def open_search(query: str) -> str:
    clean_query = query.strip()
    url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(clean_query)
    webbrowser.open_new_tab(url)
    return f"Searching the web for {clean_query}."
