"""
Lexical Cross-Reference Engine for Brahm-Kosh.

Resolves edges (dependencies) between files by tracking symbol usage.
"""

import os
import re
from typing import Dict, Set

from brahm_kosh.models import Project, FileModel, SymbolKind

# Common generic words that shouldn't trigger cross-file dependencies
# even if a user explicitly names a class/function this.
STOP_WORDS = {
    "App", "Main", "index", "Object", "String", "Array", "List", "Map", "Set",
    "run", "start", "stop", "init", "config", "data", "id", "name", "value",
    "type", "Node", "Error", "Exception"
}


def compute_lexical_dependencies(project: Project):
    """
    Populates the `.dependencies` and `.dependents` attributes on all files
    by finding lexical references to global symbols defined in other files.
    """
    files: list[FileModel] = project.all_files()
    
    # 1. Build Global Symbol Table
    # map: symbol_name -> Set[file_path]
    global_symbols: Dict[str, Set[str]] = {}

    for fm in files:
        for sym in fm.symbols:
            if sym.kind in (SymbolKind.CLASS, SymbolKind.FUNCTION):
                name = sym.name
                
                # Strip out arguments if they snuck into the name (e.g. SQL parser)
                if "(" in name:
                    name = name.split("(")[0].strip()
                    
                # Ignore very short or generic names
                if len(name) < 4 or name in STOP_WORDS:
                    continue
                    
                if name not in global_symbols:
                    global_symbols[name] = set()
                global_symbols[name].add(fm.relative_path)

    if not global_symbols:
        return

    # 2. Extract words from each file and intersect
    # We use a simple word-boundary tokenizer
    word_pattern = re.compile(r"[a-zA-Z_]\w*")
    
    # Pre-compute valid symbol names for fast intersection lookup
    valid_names = set(global_symbols.keys())

    # Create mapping of file relative path -> FileModel for quick access
    path_to_fm = {fm.relative_path: fm for fm in files}

    for fm in files:
        try:
            with open(fm.path, "r", encoding="utf-8", errors="replace") as f:
                source = f.read()
        except OSError:
            continue
            
        # Get unique words in the file
        file_words = set(word_pattern.findall(source))
        
        # Intersect with our global symbol dictionary
        matched_symbols = file_words.intersection(valid_names)
        
        for matched_sym in matched_symbols:
            target_files = global_symbols[matched_sym]
            for target_path in target_files:
                # A file does not geometrically depend on itself
                if target_path == fm.relative_path:
                    continue
                
                target_fm = path_to_fm.get(target_path)
                if not target_fm:
                    continue
                    
                # Add Forward Dependency
                if target_path not in fm.dependencies:
                    fm.dependencies.append(target_path)
                
                # Add Reverse Dependency
                if fm.relative_path not in target_fm.dependents:
                    target_fm.dependents.append(fm.relative_path)

