import requests
import json
from typing import Dict, Any, List

class EdgeComputeTool:
    """
    Atomized tool for local physical sandbox execution.
    Compliant with basic Agent Tool interface standards.
    """
    
    def __init__(self, cpolar_url: str):
        # Dynamically bind the dynamic Cpolar URL
        self.api_url = f"{cpolar_url.rstrip('/')}/solve"
        self.name = "edge_compute_sandbox"
        self.description = (
            "Execute small deterministic Python calculations in an isolated local process. "
            "Use this ONLY when deterministic calculation or code execution is required. "
            "Do NOT use this for untrusted code, file access, or general knowledge queries."
        )

    def get_tool_schema(self) -> Dict[str, Any]:
        """
        Returns the JSON Schema of the tool, ready to be injected into DeepSeek/OpenAI APIs.
        This is the core of Function Calling / MCP.
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "Python code to execute directly in the local sandbox."
                        },
                        "language": {
                            "type": "string",
                            "enum": ["python"],
                            "description": "Execution language. Only python is supported."
                        },
                        "timeout": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 10,
                            "description": "Max execution time in seconds."
                        }
                    },
                    "required": ["code"],
                    "additionalProperties": False
                }
            }
        }

    def execute(self, code: str, language: str = "python", timeout: int = 10) -> str:
        """
        The actual execution engine of the tool.
        Fires the POST request to the Edge Node.
        """
        print(f"\n[TOOL TRIGGERED] Name: {self.name} | Python code received")
        headers = {"Content-Type": "application/json"}
        payload = {
            "code": code,
            "language": language,
            "timeout": timeout
        }
        
        try:
            response = requests.post(self.api_url, headers=headers, json=payload, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return (
                    f"Tool Execution Status: {data.get('status')}. "
                    f"stdout: {data.get('stdout', '')}. stderr: {data.get('stderr', '')}"
                )
            else:
                return f"Tool Execution Failed with status code: {response.status_code}"
                
        except Exception as e:
            return f"Tool Execution Error (Edge node might be offline): {str(e)}"

class EdgeKnowledgeTool:
    def __init__(self, cpolar_url: str):
        self.api_url = f"{cpolar_url.rstrip('/')}/search"
        self.name = "edge_knowledge_rag"
        self.description = (
            "Search the local knowledge base for accurate, domain-specific context. "
            "Use this for fact lookup, textbook retrieval, or concept grounding."
        )

    def get_tool_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The query to search in the local knowledge base."
                        }
                    },
                    "required": ["query"],
                    "additionalProperties": False
                }
            }
        }

    def execute(self, query: str) -> str:
        print(f"\n[TOOL TRIGGERED] Name: {self.name} | Payload: {query}")
        headers = {"Content-Type": "application/json"}
        payload = {"query": query}
        try:
            response = requests.post(self.api_url, headers=headers, json=payload, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return f"Tool Execution Status: {data.get('status')}. Context: {data.get('context')}"
            return f"Tool Execution Failed with status code: {response.status_code}"
        except Exception as e:
            return f"Tool Execution Error (Edge node might be offline): {str(e)}"

class EdgeQuizTool:
    def __init__(self, cpolar_url: str):
        self.api_url = f"{cpolar_url.rstrip('/')}/quiz"
        self.name = "edge_quiz_generator"
        self.description = (
            "Generate a short quiz prompt based on the user's question and local knowledge context. "
            "Use this to produce a checkpoint question for learning validation."
        )

    def get_tool_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": "The learner's original question or topic."
                        },
                        "context": {
                            "type": "string",
                            "description": "Optional context to base the quiz on."
                        },
                        "n_results": {
                            "type": "integer",
                            "description": "Number of context chunks to retrieve if context is not provided."
                        },
                        "difficulty": {
                            "type": "string",
                            "enum": ["easy", "medium", "hard"],
                            "description": "Quiz difficulty level: easy (basic concepts), medium (comprehensive), hard (advanced analysis)."
                        },
                        "question_type": {
                            "type": "string",
                            "enum": ["varied", "choice", "fill", "short_answer", "true_false"],
                            "description": "Question type: varied (mixed), choice (multiple choice), fill (fill-in-blank), short_answer, true_false."
                        }
                    },
                    "required": ["question"],
                    "additionalProperties": False
                }
            }
        }

    def execute(self, question: str, context: str = "", n_results: int = 2,
                difficulty: str = "medium", question_type: str = "varied") -> str:
        headers = {"Content-Type": "application/json"}
        payload = {"question": question, "context": context, "n_results": n_results,
                   "difficulty": difficulty, "question_type": question_type}
        try:
            response = requests.post(self.api_url, headers=headers, json=payload, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return f"Tool Execution Status: {data.get('status')}. Quiz: {data.get('quiz')}"
            return f"Tool Execution Failed with status code: {response.status_code}"
        except Exception as e:
            return f"Tool Execution Error (Edge node might be offline): {str(e)}"

class EdgeGradeTool:
    def __init__(self, cpolar_url: str):
        self.api_url = f"{cpolar_url.rstrip('/')}/grade"
        self.name = "edge_answer_grader"
        self.description = (
            "Grade a learner's answer against expected keywords for quick validation. "
            "Use this to confirm understanding in the learning loop."
        )

    def get_tool_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "answer": {
                            "type": "string",
                            "description": "The learner's answer to be evaluated."
                        },
                        "keywords": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Expected keywords that should appear in the answer."
                        },
                        "min_hit": {
                            "type": "integer",
                            "description": "Minimum number of keyword hits required to pass."
                        },
                        "question_type": {
                            "type": "string",
                            "enum": ["choice", "fill", "short_answer", "true_false"],
                            "description": "Question type. Objective types are graded deterministically."
                        },
                        "expected_answer": {
                            "oneOf": [
                                {"type": "string"},
                                {"type": "boolean"},
                                {"type": "array", "items": {"type": "string"}},
                            ],
                            "description": "Correct option, boolean value, or list of fill-in answers."
                        }
                    },
                    "required": ["answer"],
                    "additionalProperties": False
                }
            }
        }

    def execute(
        self,
        answer: str,
        keywords: List[str] = None,
        min_hit: int = 1,
        question_type: str = "short_answer",
        expected_answer: Any = None,
    ) -> str:
        headers = {"Content-Type": "application/json"}
        payload = {
            "answer": answer,
            "keywords": keywords or [],
            "min_hit": min_hit,
            "question_type": question_type,
            "expected_answer": expected_answer,
        }
        try:
            response = requests.post(self.api_url, headers=headers, json=payload, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return f"Tool Execution Status: {data.get('status')}. Result: {data.get('result')}"
            return f"Tool Execution Failed with status code: {response.status_code}"
        except Exception as e:
            return f"Tool Execution Error (Edge node might be offline): {str(e)}"

def get_tool_schemas(cpolar_url: str, include_compute: bool = False) -> List[Dict[str, Any]]:
    tools = [
        EdgeKnowledgeTool(cpolar_url),
        EdgeQuizTool(cpolar_url),
        EdgeGradeTool(cpolar_url)
    ]
    if include_compute:
        tools.insert(0, EdgeComputeTool(cpolar_url))
    return [tool.get_tool_schema() for tool in tools]

if __name__ == "__main__":
    print(json.dumps(get_tool_schemas("http://127.0.0.1:8000"), indent=2))
