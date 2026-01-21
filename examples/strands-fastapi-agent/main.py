"""
Strands Agent + nlp2sql + FastAPI Demo

This project demonstrates the integration of:
- nlp2sql: Natural language to SQL conversion library
- Strands Agents: AI agent framework with tool calling
- FastAPI: Modern async web framework

The API exposes both direct nlp2sql endpoints and an AI agent
that intelligently uses tools to answer database questions.
"""

from fastapi import FastAPI
from strands import Agent, tool
from strands.models.openai import OpenAIModel
import os
import json
import logging
from pydantic import BaseModel
from nlp2sql import create_and_initialize_service, DatabaseType
from contextlib import asynccontextmanager
from dotenv import load_dotenv


# =============================================================================
# Configuration
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

load_dotenv()


# =============================================================================
# Request Models
# =============================================================================

class ChatRequest(BaseModel):
    """Request model for chat endpoint."""
    message: str


class GenerateSQLRequest(BaseModel):
    """Request model for SQL generation."""
    question: str


class ExecuteSQLRequest(BaseModel):
    """Request model for direct SQL execution."""
    sql: str


# =============================================================================
# Global State
# =============================================================================

nlp2sql_service = None
database_type_global = DatabaseType.POSTGRES


# =============================================================================
# Application Lifecycle
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize nlp2sql service on startup."""
    global nlp2sql_service, database_type_global

    # Detect AI provider from available API keys
    api_key = (
        os.getenv("OPENAI_API_KEY")
        or os.getenv("ANTHROPIC_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
    )
    provider = (
        "openai" if os.getenv("OPENAI_API_KEY")
        else "anthropic" if os.getenv("ANTHROPIC_API_KEY")
        else "gemini"
    )

    database_url = os.getenv("DATABASE_URL")
    schema_name = os.getenv("SCHEMA_NAME", "public")
    database_type_str = os.getenv("DATABASE_TYPE", "POSTGRES")
    database_type = getattr(DatabaseType, database_type_str.upper(), DatabaseType.POSTGRES)
    database_type_global = database_type

    if not database_url:
        raise ValueError("DATABASE_URL environment variable is not set")

    if not api_key:
        raise ValueError(
            "No API key found. Set OPENAI_API_KEY, ANTHROPIC_API_KEY, or GOOGLE_API_KEY"
        )

    try:
        nlp2sql_service = await create_and_initialize_service(
            database_url=database_url,
            ai_provider=provider,
            api_key=api_key,
            database_type=database_type,
            embedding_provider_type="local",
            schema_name=schema_name,
        )
        logger.info(f"nlp2sql initialized with {provider} provider, schema: {schema_name}")
    except Exception as e:
        logger.error(f"Failed to initialize nlp2sql service: {e}")
        raise

    yield


# =============================================================================
# FastAPI App
# =============================================================================

app = FastAPI(
    title="Strands Agent + nlp2sql Demo",
    description="""
Demo API showcasing the integration of:
- **nlp2sql**: Natural language to SQL conversion
- **Strands Agents**: AI agents with tool calling capabilities  
- **FastAPI**: Modern async Python web framework

## Endpoints

### Direct nlp2sql Endpoints (no agent)
- `GET /tables` - List database tables
- `POST /tools/generate-sql` - Convert question to SQL
- `POST /tools/execute-sql` - Execute raw SQL query
- `POST /tools/query` - Generate and execute SQL in one step

### Strands Agent Endpoint
- `POST /agent/chat` - Chat with AI agent that uses tools intelligently
    """,
    version="1.0.0",
    lifespan=lifespan,
)


# =============================================================================
# Strands Agent Tools
# =============================================================================

@tool
async def generate_sql_tool(question: str) -> str:
    """Generate SQL query from natural language question.
    
    Use this tool when the user asks a question about the database
    or wants to query data. This will convert their question to SQL.
    
    Args:
        question: Natural language question about the database
        
    Returns:
        JSON string with sql, confidence, and explanation
    """
    if nlp2sql_service is None:
        return json.dumps({"error": "Database service not initialized"})
    
    try:
        result = await nlp2sql_service.generate_sql(
            question=question, database_type=database_type_global
        )
        return json.dumps({
            "sql": result["sql"],
            "confidence": result["confidence"],
            "explanation": result.get("explanation", ""),
        })
    except Exception as e:
        logger.error(f"SQL generation error: {e}")
        return json.dumps({"error": str(e)})


@tool
async def execute_sql_tool(sql_query: str) -> str:
    """Execute a SQL query and return results.
    
    Use this tool after generating SQL to actually execute it
    and get the data from the database.
    
    Args:
        sql_query: SQL query to execute (must be SELECT only)
        
    Returns:
        JSON string with results, columns, and row_count
    """
    if nlp2sql_service is None:
        return json.dumps({"error": "Database service not initialized"})
    
    try:
        execution_result = await nlp2sql_service.schema_repository.execute_query(sql_query)
        return json.dumps({
            "success": True,
            "data": execution_result.get("results", []),
            "columns": execution_result.get("columns", []),
            "row_count": execution_result.get("row_count", 0),
        })
    except Exception as e:
        logger.error(f"SQL execution error: {e}")
        return json.dumps({"success": False, "error": str(e)})


@tool
async def list_tables_tool() -> str:
    """List all available tables in the database.
    
    Use this tool when the user asks about what tables are available
    or wants to know the database structure.
    
    Returns:
        JSON string with list of table names
    """
    if nlp2sql_service is None:
        return json.dumps({"error": "Database service not initialized"})
    
    try:
        repository = nlp2sql_service.schema_repository
        tables = await repository.get_tables()
        table_names = [table.name for table in tables]
        return json.dumps({
            "success": True,
            "schema": repository.schema_name,
            "tables": table_names,
            "count": len(table_names),
        })
    except Exception as e:
        logger.error(f"Error listing tables: {e}")
        return json.dumps({"success": False, "error": str(e)})


# =============================================================================
# Strands Agent
# =============================================================================

# OpenAI model for the agent (reads API key from environment)
model = OpenAIModel(model_id="gpt-4o-mini")

# Create agent with database tools
agent = Agent(
    name="E-commerce Analytics Agent",
    model=model,
    tools=[generate_sql_tool, execute_sql_tool, list_tables_tool],
    system_prompt="""You are an e-commerce analytics assistant with access to a database.
    
When users ask questions about data:
1. First use list_tables_tool if you need to understand the schema
2. Use generate_sql_tool to convert their question to SQL
3. Use execute_sql_tool to run the query and get results
4. Present the results in a clear, human-readable format

Be concise and focus on answering the user's question with the data."""
)


# =============================================================================
# API Endpoints - Root
# =============================================================================

@app.get("/", tags=["Info"])
def read_root():
    """API information and available endpoints."""
    return {
        "name": "Strands Agent + nlp2sql Demo",
        "description": "Natural language database queries with AI agents",
        "endpoints": {
            "info": {
                "GET /": "This information",
                "GET /health": "Health check",
                "GET /tables": "List database tables",
            },
            "tools": {
                "POST /tools/generate-sql": "Convert question to SQL (nlp2sql)",
                "POST /tools/execute-sql": "Execute raw SQL query",
                "POST /tools/query": "Generate and execute SQL in one step",
            },
            "agent": {
                "POST /agent/chat": "Chat with Strands AI agent",
            }
        }
    }


@app.get("/health", tags=["Info"])
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "nlp2sql_initialized": nlp2sql_service is not None,
        "schema": nlp2sql_service.schema_repository.schema_name if nlp2sql_service else None,
    }


# =============================================================================
# API Endpoints - Direct Tool Access (no agent)
# =============================================================================

@app.get("/tables", tags=["Tools"])
async def get_tables():
    """List all available tables in the database.
    
    This endpoint directly uses nlp2sql to list tables without the agent.
    """
    if nlp2sql_service is None:
        return {"error": "Service not initialized"}

    try:
        repository = nlp2sql_service.schema_repository
        tables = await repository.get_tables()
        return {
            "success": True,
            "schema": repository.schema_name,
            "tables": [
                {
                    "name": t.name,
                    "columns": len(t.columns),
                    "description": t.description,
                }
                for t in tables
            ],
            "count": len(tables),
        }
    except Exception as e:
        logger.error(f"Error listing tables: {e}")
        return {"success": False, "error": str(e)}


@app.post("/tools/generate-sql", tags=["Tools"])
async def generate_sql(request: GenerateSQLRequest):
    """Generate SQL from natural language question.
    
    This endpoint directly uses nlp2sql to generate SQL without the agent.
    It does NOT execute the query - use /tools/execute-sql or /tools/query for that.
    """
    if nlp2sql_service is None:
        return {"error": "Service not initialized"}

    try:
        result = await nlp2sql_service.generate_sql(
            question=request.question,
            database_type=database_type_global
        )
        return {
            "success": True,
            "question": request.question,
            "sql": result["sql"],
            "confidence": result["confidence"],
            "explanation": result.get("explanation", ""),
        }
    except Exception as e:
        logger.error(f"SQL generation error: {e}")
        return {"success": False, "error": str(e)}


@app.post("/tools/execute-sql", tags=["Tools"])
async def execute_sql(request: ExecuteSQLRequest):
    """Execute a raw SQL query.
    
    This endpoint directly executes SQL without the agent.
    Only SELECT queries are allowed for security.
    """
    if nlp2sql_service is None:
        return {"error": "Service not initialized"}

    try:
        result = await nlp2sql_service.schema_repository.execute_query(request.sql)
        return {
            "success": True,
            "sql": request.sql,
            "columns": result.get("columns", []),
            "data": result.get("results", []),
            "row_count": result.get("row_count", 0),
            "execution_time_ms": result.get("execution_time_ms"),
        }
    except Exception as e:
        logger.error(f"SQL execution error: {e}")
        return {"success": False, "error": str(e)}


@app.post("/tools/query", tags=["Tools"])
async def query_database(request: GenerateSQLRequest):
    """Generate SQL and execute it in one step.
    
    This endpoint combines generate-sql and execute-sql for convenience.
    It uses nlp2sql directly without the Strands agent.
    """
    if nlp2sql_service is None:
        return {"error": "Service not initialized"}

    try:
        # Generate SQL
        sql_result = await nlp2sql_service.generate_sql(
            question=request.question,
            database_type=database_type_global
        )
        sql_query = sql_result["sql"]
        
        # Execute SQL
        execution_result = await nlp2sql_service.schema_repository.execute_query(sql_query)
        
        return {
            "success": True,
            "question": request.question,
            "sql": sql_query,
            "confidence": sql_result["confidence"],
            "explanation": sql_result.get("explanation", ""),
            "columns": execution_result.get("columns", []),
            "data": execution_result.get("results", []),
            "row_count": execution_result.get("row_count", 0),
        }
    except Exception as e:
        logger.error(f"Query error: {e}")
        return {"success": False, "error": str(e)}


# =============================================================================
# API Endpoints - Strands Agent
# =============================================================================

@app.post("/agent/chat", tags=["Agent"])
async def agent_chat(request: ChatRequest):
    """Chat with the Strands AI agent.
    
    The agent intelligently decides which tools to use based on your message.
    It can:
    - List available tables
    - Generate SQL from natural language
    - Execute queries and present results
    
    This demonstrates Strands Agents' tool-calling capabilities.
    """
    try:
        result = await agent.invoke_async(request.message)
        return {
            "success": True,
            "message": request.message,
            "response": str(result),
        }
    except Exception as e:
        logger.error(f"Agent chat error: {e}")
        return {
            "success": False,
            "message": request.message,
            "error": str(e),
        }


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
