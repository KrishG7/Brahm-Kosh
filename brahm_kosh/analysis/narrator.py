import random
from brahm_kosh.models import FileModel
from brahm_kosh.analysis.hotspots import Hotspot

def generate_narration(file_model: FileModel) -> str:
    """
    Step B: AI Narration (The Flesh)
    Deterministically generates a plain-English explanation of a file's role
    by reading its parsed skeleton (symbols, complexity, dependencies).
    
    This acts as a fast, offline LLM substitute.
    """
    
    # 1. Base Purpose
    purpose = file_model.purpose or "Generic Utility"
    narration = f"This file functions primarily as a {purpose.lower()} module. "
    
    # 2. Structural Content
    symbol_count = len(file_model.symbols)
    if symbol_count == 0:
        narration += "It does not expose any distinct classes or functions, suggesting it either acts as a configuration file, a script, or simply re-exports functionality. "
    elif symbol_count == 1:
        sym = file_model.symbols[0]
        narration += f"It encapsulates a single core component (`{sym.name}`), adhering to the single responsibility principle. "
    else:
        # List up to 3 symbols
        top_syms = [s.name for s in file_model.symbols[:3]]
        sym_list = ", ".join(f"`{s}`" for s in top_syms)
        if symbol_count > 3:
            sym_list += f", and {symbol_count - 3} others"
        narration += f"It exposes {symbol_count} primary objects (including {sym_list}). "

    # 3. Complexity & Heat
    heat = file_model.heat
    if heat == "Critical":
        narration += "Structurally, this code is dangerously tightly coupled and deeply entangled. It requires immediate refactoring. "
    elif heat == "High":
        narration += "It has a high complexity score, indicating it might be taking on too many responsibilities. "
    elif heat == "Low" or heat == "Optimal":
        narration += "The code footprint is small and optimal, suggesting a clean, highly modular design. "
        
    # 4. Dependency Context (if available in future, but we map that via edge graphs)
    
    return narration.strip()
