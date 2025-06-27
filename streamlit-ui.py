import streamlit as st
import os
from langgraph.checkpoint.memory import MemorySaver
from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv
from langchain_tavily import TavilySearch
from scrapegraph_py import Client
from langchain_core.messages import HumanMessage, AIMessage
import time

# Load environment variables
load_dotenv()

# Page configuration

st.set_page_config(
    page_title="Web Search & Scrape Bot",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        text-align: center;
        padding: 2rem 0;
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        color: white;
        border-radius: 10px;
        margin-bottom: 2rem;
    }
    
    .url-box {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #4CAF50;
        margin: 0.5rem 0;
    }
    
    .error-box {
        background-color: #ffebee;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #f44336;
        margin: 0.5rem 0;
    }
    
    .success-box {
        background-color: #e8f5e8;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #4CAF50;
        margin: 0.5rem 0;
    }
    
    .step-indicator {
        display: flex;
        justify-content: space-between;
        margin: 2rem 0;
    }
    
    .step {
        flex: 1;
        text-align: center;
        padding: 1rem;
        background-color: #f0f2f6;
        margin: 0 0.5rem;
        border-radius: 8px;
        position: relative;
    }
    
    .step.active {
        background-color: #4CAF50;
        color: white;
    }
    
    .step.completed {
        background-color: #2196F3;
        color: white;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'messages' not in st.session_state:
    st.session_state.messages = []
if 'search_results' not in st.session_state:
    st.session_state.search_results = []
if 'extracted_data' not in st.session_state:
    st.session_state.extracted_data = []
if 'current_step' not in st.session_state:
    st.session_state.current_step = 0

# State definition for LangGraph
class State(TypedDict):
    user_input: str
    messages: Annotated[list, add_messages]
    urls: list[str]
    extracted: list[str]

# Initialize components
@st.cache_resource
def initialize_components():
    """Initialize LLM, search tool, and other components"""
    try:
        os.environ["GOOGLE_API_KEY"] = os.getenv("GOOGLE_API_KEY")
        os.environ["TAVILY_API_KEY"] = os.getenv("TAVILY_API_KEY")
        
        llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash")
        tool = TavilySearch(max_results=2)
        memory = MemorySaver()
        sg = os.getenv("SG")
        
        return llm, tool, memory, sg
    except Exception as e:
        st.error(f"Error initializing components: {e}")
        return None, None, None, None

# LangGraph functions
def web_search(state: State, tool):
    """Search the web for relevant URLs based on user input"""
    try:
        tools_res = tool.invoke(state["user_input"])
        urls = [result["url"] for result in tools_res["results"]]
        return {"urls": urls}
    except Exception as e:
        st.error(f"Search error: {e}")
        return {"urls": []}

def scrape_data(state: State, sg_api_key):
    """Scrape data from the found URLs"""
    client = Client(api_key=sg_api_key)
    extracted_data = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, url in enumerate(state["urls"]):
        try:
            status_text.text(f"Scraping URL {i+1}/{len(state['urls'])}: {url}")
            progress_bar.progress((i + 1) / len(state["urls"]))
            
            response = client.smartscraper(
                website_url=url,
                user_prompt="Extract the main content, key information, and relevant details from this webpage"
            )
            
            if isinstance(response, dict):
                content = response.get('content', str(response))
            else:
                content = str(response)
                
            extracted_data.append({
                "url": url,
                "content": content,
                "status": "success"
            })
            
        except Exception as e:
            extracted_data.append({
                "url": url,
                "content": f"Error: Could not extract content from this URL - {str(e)}",
                "status": "error"
            })
    
    progress_bar.empty()
    status_text.empty()
    
    return {"extracted": extracted_data}

def generate_response(state: State, llm):
    """Generate AI response based on extracted data and user input"""
    context_parts = []
    for item in state["extracted"]:
        if item["status"] == "success":
            context_parts.append(f"URL: {item['url']}\nContent: {item['content']}")
    
    context = "\n\n".join(context_parts) if context_parts else "No data was successfully extracted from the URLs."
    
    prompt = f"""
User Question: {state['user_input']}

Based on the following extracted web content, please provide a comprehensive and helpful answer:

{context}

Please provide a clear, well-structured response that directly addresses the user's question using the information found in the web content. If the extracted content doesn't fully answer the question, please indicate what information is missing.
"""
    
    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        return response.content
    except Exception as e:
        return f"I apologize, but I encountered an error while processing your request: {e}"

# Main UI
def main():
    # Header
    st.markdown("""
    <div class="main-header">
        <h1>🔍 Web Search & Scrape Bot</h1>
        <p>Search the web, extract content, and get AI-powered answers</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Initialize components
    llm, tool, memory, sg_api_key = initialize_components()
    
    if not all([llm, tool, sg_api_key]):
        st.error("⚠️ Please check your environment variables and API keys!")
        st.stop()
    
    # Sidebar for settings and info
    with st.sidebar:
        st.header("⚙️ Settings")
        
        # API Status
        st.subheader("API Status")
        st.success("✅ Google Gemini API")
        st.success("✅ Tavily Search API")
        st.success("✅ ScrapeGraph API")
        
        # Clear chat history
        if st.button("🗑️ Clear Chat History"):
            st.session_state.messages = []
            st.session_state.search_results = []
            st.session_state.extracted_data = []
            st.session_state.current_step = 0
            st.rerun()
        
        # Help section
        st.subheader("ℹ️ How it works")
        st.markdown("""
        1. **Search**: Enter your question
        2. **Find**: Search the web for relevant URLs
        3. **Extract**: Scrape content from found pages
        4. **Answer**: AI generates response based on extracted data
        """)
    
    # Main chat interface
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("💬 Chat")
        
        # Display chat messages
        chat_container = st.container()
        with chat_container:
            for message in st.session_state.messages:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])
        
        # Chat input
        if prompt := st.chat_input("Ask me anything..."):
            # Add user message to chat
            st.session_state.messages.append({"role": "user", "content": prompt})
            
            with st.chat_message("user"):
                st.markdown(prompt)
            
            # Process the query
            with st.chat_message("assistant"):
                with st.spinner("Processing your request..."):
                    
                    # Step 1: Web Search
                    st.write("🔍 **Step 1: Searching the web...**")
                    state = State(user_input=prompt, messages=[], urls=[], extracted=[])
                    search_result = web_search(state, tool)
                    state["urls"] = search_result["urls"]
                    
                    if state["urls"]:
                        st.success(f"Found {len(state['urls'])} relevant URLs")
                        st.session_state.search_results = state["urls"]
                    else:
                        st.error("No URLs found for your query")
                        return
                    
                    # Step 2: Scrape Data
                    st.write("🕷️ **Step 2: Extracting content...**")
                    extract_result = scrape_data(state, sg_api_key)
                    state["extracted"] = extract_result["extracted"]
                    st.session_state.extracted_data = state["extracted"]
                    
                    # Step 3: Generate Response
                    st.write("🤖 **Step 3: Generating AI response...**")
                    ai_response = generate_response(state, llm)
                    
                    # Display the final response
                    st.markdown("### 📝 **Final Answer:**")
                    st.markdown(ai_response)
                    
                    # Add AI response to chat
                    st.session_state.messages.append({"role": "assistant", "content": ai_response})
    
    with col2:
        st.subheader("🔗 Search Results")
        
        if st.session_state.search_results:
            for i, url in enumerate(st.session_state.search_results):
                st.markdown(f"""
                <div class="url-box">
                    <strong>URL {i+1}:</strong><br>
                    <a href="{url}" target="_blank">{url}</a>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No search results yet. Ask a question to get started!")
        
        st.subheader("📊 Extraction Status")
        
        if st.session_state.extracted_data:
            for i, item in enumerate(st.session_state.extracted_data):
                if item["status"] == "success":
                    st.markdown(f"""
                    <div class="success-box">
                        <strong>✅ URL {i+1}: Success</strong><br>
                        Content length: {len(item['content'])} characters
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div class="error-box">
                        <strong>❌ URL {i+1}: Failed</strong><br>
                        {item['content']}
                    </div>
                    """, unsafe_allow_html=True)
        else:
            st.info("No extraction data yet.")
        
        # Show extracted content in expander
        if st.session_state.extracted_data:
            with st.expander("📄 View Extracted Content"):
                for i, item in enumerate(st.session_state.extracted_data):
                    st.subheader(f"URL {i+1}")
                    st.write(f"**Source:** {item['url']}")
                    st.write(f"**Status:** {item['status']}")
                    st.text_area(
                        f"Content {i+1}",
                        value=item['content'][:1000] + "..." if len(item['content']) > 1000 else item['content'],
                        height=200,
                        key=f"content_{i}"
                    )
                    st.markdown("---")

# Environment variable checker
def check_environment():
    """Check if all required environment variables are set"""
    required_vars = ["GOOGLE_API_KEY", "TAVILY_API_KEY", "SG"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        st.error(f"❌ Missing environment variables: {', '.join(missing_vars)}")
        st.markdown("""
        Please set the following environment variables:
        - `GOOGLE_API_KEY`: Your Google Gemini API key
        - `TAVILY_API_KEY`: Your Tavily Search API key  
        - `SG`: Your ScrapeGraph API key
        
        You can set these in a `.env` file or as system environment variables.
        """)
        return False
    return True

if __name__ == "__main__":
    if check_environment():
        main()
    else:
        st.stop()