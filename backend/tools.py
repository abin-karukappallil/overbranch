import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from langchain_core.tools import tool

logger = logging.getLogger("tools")

class EditChunkArgs(BaseModel):
    chunk_index: int = Field(description="1-based index of the target retrieved CHUNK [CHUNK 1..8]")
    target_text: str = Field(..., description="EXACT verbatim substring from the retrieved chunk to replace")
    replacement_code: str = Field(..., description="Updated or replacement LaTeX code")
    rationale: str = Field(..., description="Explanation of why this edit was made")

class CreateContentArgs(BaseModel):
    new_code: str = Field(..., description="Complete generated LaTeX snippet or Beamer slide frames")
    anchor_chunk_index: Optional[int] = Field(None, description="Optional 1-based index of chunk to insert after/before")
    position: str = Field("end", description="Insertion position: 'end', 'after_anchor', or 'before_anchor'")
    rationale: str = Field(..., description="Explanation of the generated content")

class DeleteChunkArgs(BaseModel):
    chunk_index: int = Field(..., description="1-based index of the target retrieved CHUNK [CHUNK 1..8]")
    target_text: str = Field(..., description="EXACT verbatim substring from the chunk to remove")
    rationale: str = Field(..., description="Explanation of why this text is being deleted")

class FindReplaceAllArgs(BaseModel):
    search_pattern: str = Field(..., description="Exact verbatim text or term to find everywhere in the document")
    replacement_pattern: str = Field(..., description="Replacement text or term to use instead")
    rationale: str = Field(..., description="Explanation of the global find and replace")

@tool("edit_chunk", args_schema=EditChunkArgs)
def edit_chunk(chunk_index: int, target_text: str, replacement_code: str, rationale: str) -> Dict[str, Any]:
    print(f"\n🛠️  [TOOL EXECUTION: edit_chunk]\n  ► CHUNK Index: {chunk_index}\n  ► Target Text: '{target_text}'\n  ► Replacement: '{replacement_code[:60]}...'\n  ► Rationale: {rationale}\n")
    return {
        "action": "edit",
        "chunk_index": chunk_index,
        "original_chunk": target_text,
        "proposed_chunk": replacement_code,
        "explanation": rationale,
    }

@tool("create_content", args_schema=CreateContentArgs)
def create_content(new_code: str, anchor_chunk_index: Optional[int] = None, position: str = "end", rationale: str = "") -> Dict[str, Any]:
    print(f"\n✨ [TOOL EXECUTION: create_content]\n  ► Anchor CHUNK: {anchor_chunk_index}\n  ► Position: {position}\n  ► New Code Preview: '{new_code[:80]}...'\n  ► Rationale: {rationale}\n")
    return {
        "action": "create",
        "chunk_index": anchor_chunk_index,
        "original_chunk": "",
        "proposed_chunk": new_code,
        "explanation": rationale or "Generated new LaTeX content.",
    }

@tool("delete_chunk", args_schema=DeleteChunkArgs)
def delete_chunk(chunk_index: int, target_text: str, rationale: str) -> Dict[str, Any]:
    print(f"\n🗑️  [TOOL EXECUTION: delete_chunk]\n  ► CHUNK Index: {chunk_index}\n  ► Target to Delete: '{target_text}'\n  ► Rationale: {rationale}\n")
    return {
        "action": "delete",
        "chunk_index": chunk_index,
        "original_chunk": target_text,
        "proposed_chunk": "",
        "explanation": rationale,
    }

@tool("find_and_replace_all", args_schema=FindReplaceAllArgs)
def find_and_replace_all(search_pattern: str, replacement_pattern: str, rationale: str) -> Dict[str, Any]:
    print(f"\n🔍 [TOOL EXECUTION: find_and_replace_all]\n  ► Search Pattern: '{search_pattern}'\n  ► Replacement: '{replacement_pattern}'\n  ► Rationale: {rationale}\n")
    return {
        "action": "global_replace",
        "search_pattern": search_pattern,
        "replacement_pattern": replacement_pattern,
        "original_chunk": search_pattern,
        "proposed_chunk": replacement_pattern,
        "explanation": rationale,
    }

class SearchChunksArgs(BaseModel):
    query: str = Field(..., description="Semantic query to search Qdrant vector DB for document chunks")

@tool("search_document_chunks", args_schema=SearchChunksArgs)
def search_document_chunks(query: str) -> Dict[str, Any]:
    print(f"\n🔎 [TOOL EXECUTION: search_document_chunks]\n  ► Vector Query: '{query}'\n")
    return {
        "action": "search_chunks",
        "query": query,
        "explanation": f"Searching vector DB for query '{query}'",
    }

AI_TOOLS = [search_document_chunks, edit_chunk, create_content, delete_chunk, find_and_replace_all]

def process_tool_calls(tool_calls: List[Dict[str, Any]], retrieved_chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    print(f"\n⚙️  [TOOL PROCESSOR] Received {len(tool_calls)} raw tool call(s) from LLM:")
    if not tool_calls:
        print("  ⚠️  No tool calls to process.")
        return {}

    edits = []
    plans = []

    for call in tool_calls:
        tool_name = call.get("name") or call.get("function", {}).get("name", "")
        args = call.get("args") or call.get("function", {}).get("arguments", {})

        if isinstance(args, str):
            import json
            try:
                args = json.loads(args)
            except Exception:
                args = {}

        if tool_name == "edit_chunk":
            orig = args.get("target_text", "")
            prop = args.get("replacement_code", "")
            exp = args.get("rationale", "Edit chunk")
            idx = args.get("chunk_index")
            edits.append({
                "chunk_index": idx,
                "original_chunk": orig,
                "proposed_chunk": prop,
                "explanation": exp,
            })
            plans.append(f"Edit CHUNK {idx}: replace '{orig[:30]}...' with updated LaTeX.")

        elif tool_name == "create_content":
            prop = args.get("new_code", "")
            exp = args.get("rationale", "Create new content")
            idx = args.get("anchor_chunk_index")
            edits.append({
                "chunk_index": idx,
                "original_chunk": "",
                "proposed_chunk": prop,
                "explanation": exp,
            })
            plans.append("Create new LaTeX content/slides.")

        elif tool_name == "delete_chunk":
            orig = args.get("target_text", "")
            exp = args.get("rationale", "Delete text")
            idx = args.get("chunk_index")
            edits.append({
                "chunk_index": idx,
                "original_chunk": orig,
                "proposed_chunk": "",
                "explanation": exp,
            })
            plans.append(f"Delete '{orig[:30]}...' from CHUNK {idx}.")

        elif tool_name == "find_and_replace_all":
            search_pat = args.get("search_pattern", "")
            replace_pat = args.get("replacement_pattern", "")
            exp = args.get("rationale", "Global find and replace")

            found_any = False
            for c in retrieved_chunks:
                c_idx = c.get("chunk_index", 0) + 1
                c_content = c.get("content", "")
                if search_pat and search_pat in c_content:
                    found_any = True
                    edits.append({
                        "chunk_index": c_idx,
                        "original_chunk": search_pat,
                        "proposed_chunk": replace_pat,
                        "explanation": f"Global replace in CHUNK {c_idx}: {exp}",
                    })
            if not found_any and search_pat:
                edits.append({
                    "chunk_index": None,
                    "original_chunk": search_pat,
                    "proposed_chunk": replace_pat,
                    "explanation": exp,
                })
            plans.append(f"Global replace '{search_pat}' -> '{replace_pat}'.")

    first_orig = edits[0].get("original_chunk", "") if edits else ""
    first_prop = edits[0].get("proposed_chunk", "") if edits else ""
    overall_exp = "; ".join([e.get("explanation", "") for e in edits]) if edits else "Processed tool calls."

    return {
        "plan": " | ".join(plans),
        "edits": edits,
        "original_chunk": first_orig,
        "proposed_chunk": first_prop,
        "explanation": overall_exp,
    }
