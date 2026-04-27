from brahm_kosh.models import FileModel


def generate_narration(file_model: FileModel) -> str:
    """
    Deterministic, template-based summary of a file's role, derived from
    its parsed skeleton (purpose, symbols, complexity).

    Not an LLM — a rule-driven narrator. Cheap, offline, reproducible.
    """
    purpose = file_model.purpose or "Generic Utility"
    narration = f"This file functions primarily as a {purpose.lower()} module. "

    symbol_count = len(file_model.symbols)
    if symbol_count == 0:
        narration += (
            "It exposes no distinct classes or functions, suggesting it acts "
            "as a configuration file, a script, or a re-export stub. "
        )
    elif symbol_count == 1:
        sym = file_model.symbols[0]
        narration += (
            f"It encapsulates a single core component (`{sym.name}`), "
            "adhering to the single-responsibility principle. "
        )
    else:
        top_syms = [s.name for s in file_model.symbols[:3]]
        sym_list = ", ".join(f"`{s}`" for s in top_syms)
        if symbol_count > 3:
            sym_list += f", and {symbol_count - 3} others"
        narration += f"It exposes {symbol_count} primary objects (including {sym_list}). "

    heat = file_model.heat_label
    if heat == "Critical":
        narration += (
            "Structurally it is deeply entangled and branches heavily — a "
            "strong refactoring candidate. "
        )
    elif heat == "High":
        narration += (
            "It has a high complexity score, so it may be taking on too many "
            "responsibilities. "
        )
    elif heat in ("Low", "Optimal"):
        narration += "Its footprint is small, suggesting a clean, modular design. "

    return narration.strip()
