import re
from typing import List, Dict, Set, Optional, Any
from bs4 import BeautifulSoup

class AriaSnapshotFilter:
    INTERACTIVE_ROLES = {
        'button', 'link', 'textbox', 'searchbox', 'combobox', 'checkbox',
        'radio', 'switch', 'slider', 'tab', 'menuitem', 'option',
    }

    @staticmethod
    def parse_playwright_snapshot(snapshot_text: str) -> List[Dict[str, Any]]:
        lines = snapshot_text.split('\n')
        elements = []
        i = 0
        while i < len(lines):
            line = lines[i]
            trimmed = line.strip()
            
            if not trimmed or not trimmed.startswith('-'):
                i += 1
                continue
            
            # Extract Ref: [ref=123]
            ref_match = re.search(r'\[ref=([^\\\]]+)\]', trimmed)
            if not ref_match:
                i += 1
                continue
            ref = ref_match.group(1)
            
            # Extract Role: - button "Submit"
            role_match = re.match(r'^-\s+([a-zA-Z]+)', trimmed)
            if not role_match:
                i += 1
                continue
            role = role_match.group(1)
            
            if role not in AriaSnapshotFilter.INTERACTIVE_ROLES:
                i += 1
                continue
                
            # Extract Name: "Submit"
            name_match = re.search(r'"([^"]*)"', trimmed)
            name = name_match.group(1) if name_match else ''
            
            # Extract URL (next line usually)
            url = None
            if i + 1 < len(lines):
                next_line = lines[i+1]
                url_match = re.search(r'/url:\s*(.+)', next_line)
                if url_match:
                    url = url_match.group(1).strip().strip('"\'')
            
            elements.append({
                'ref': ref,
                'role': role,
                'name': name,
                'url': url
            })
            i += 1
            
        return elements

    @staticmethod
    def format_compact(elements: List[Dict[str, Any]]) -> str:
        lines = []
        for el in elements:
            parts = [f'[{el["ref"]}]', el['role']]
            
            if el.get('name'):
                name = el['name']
                if len(name) > 60:
                    name = name[:57] + '...'
                parts.append(f'"{name}"')
                
            if el.get('url') and not el['url'].startswith('#'):
                url = el['url']
                if len(url) > 50:
                    url = url[:47] + '...'
                parts.append(f"-> {url}")
                
            lines.append(' '.join(parts))
            
        return '\n'.join(lines)

    @classmethod
    def filter_snapshot(cls, snapshot_text: str) -> str:
        try:
            elements = cls.parse_playwright_snapshot(snapshot_text)
            if not elements:
                return 'No interactive elements found'
            return cls.format_compact(elements)
        except Exception as e:
            return f"Error filtering snapshot: {str(e)}"

    @staticmethod
    def format_dom_elements(elements: List[Dict[str, Any]]) -> Optional[str]:
        if not elements:
            return None
        return AriaSnapshotFilter.format_compact(elements)
