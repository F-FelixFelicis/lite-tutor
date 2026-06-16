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
            "Execute complex math, physics, or coding tasks in a secure local physical sandbox. "
            "Use this ONLY when deterministic calculation or code execution is required. "
            "Do NOT use this for general knowledge queries."
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
                        "task_instruction": {
                            "type": "string",
                            "description": "The natural language instruction or math problem for the physical machine to solve (e.g., 'Calculate 2^10')."
                        },
                        "code": {
                            "type": "string",
                            "description": "Python code to execute directly in the local sandbox."
                        },
                        "language": {
                            "type": "string",
                            "description": "Execution language. Only python is supported."
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Max execution time in seconds."
                        }
                    },
                    "required": [],
                    "additionalProperties": False
                }
            }
        }

    def execute(self, task_instruction: str = "", code: str = "", language: str = "python", timeout: int = 20) -> str:
        """
        The actual execution engine of the tool.
        Fires the POST request to the Edge Node.
        """
        print(f"\n[TOOL TRIGGERED] Name: {self.name} | Payload: {task_instruction or code}")
        headers = {"Content-Type": "application/json"}
        payload = {
            "task_instruction": task_instruction,
            "code": code,
            "language": language,
            "timeout": timeout
        }
        
        try:
            # Fire-and-forget request with a short timeout to prevent blocking the LLM
            response = requests.post(self.api_url, headers=headers, json=payload, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return f"Tool Execution Status: {data.get('status')}. Receipt: {data.get('solution')}"
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
                        }
                    },
                    "required": ["answer"],
                    "additionalProperties": False
                }
            }
        }

    def execute(self, answer: str, keywords: List[str] = None, min_hit: int = 1) -> str:
        headers = {"Content-Type": "application/json"}
        payload = {
            "answer": answer,
            "keywords": keywords or [],
            "min_hit": min_hit
        }
        try:
            response = requests.post(self.api_url, headers=headers, json=payload, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return f"Tool Execution Status: {data.get('status')}. Result: {data.get('result')}"
            return f"Tool Execution Failed with status code: {response.status_code}"
        except Exception as e:
            return f"Tool Execution Error (Edge node might be offline): {str(e)}"

def get_tool_schemas(cpolar_url: str) -> List[Dict[str, Any]]:
    tools = [
        EdgeComputeTool(cpolar_url),
        EdgeKnowledgeTool(cpolar_url),
        EdgeQuizTool(cpolar_url),
        EdgeGradeTool(cpolar_url)
    ]
    return [tool.get_tool_schema() for tool in tools]

# Quick Local Test Block
if __name__ == "__main__":
    # Replace with your current active Cpolar URL
    TEST_CPOLAR_URL = "https://tutor.vip.cpolar.cn" 
    
    # Initialize the weapon
    sandbox_tool = EdgeComputeTool(TEST_CPOLAR_URL)
    
    # Check the schema (What the LLM sees)
    print("--- Tool Schema (For LLM) ---")
    print(json.dumps(sandbox_tool.get_tool_schema(), indent=2))
    
    # Pull the trigger (What happens when the LLM calls it)
    print("\n--- Testing Execution ---")
    result = sandbox_tool.execute("Write a Python code to calculate 2 to the power of 10 and print GeekDay")
    print(f"Return to LLM:\n{result}")
