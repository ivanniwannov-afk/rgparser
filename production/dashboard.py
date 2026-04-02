"""Be[Sales] Proprietary Intelligence System - Dashboard Interface."""

import streamlit as st
import json
import asyncio
import aiosqlite
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Tuple


# ============================================================================
# STEALTH DESIGN 2026 - CSS INJECTION
# ============================================================================

STEALTH_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600&display=swap');

* {
    font-family: 'JetBrains Mono', monospace !important;
}

/* Hide Streamlit defaults */
#MainMenu, header, footer {
    visibility: hidden;
}

/* Remove top padding for edge-to-edge design */
.block-container {
    padding-top: 0rem !important;
    padding-bottom: 2rem;
}

/* Global background */
body, .stApp {
    background-color: #0A0A0A;
    color: #FFFFFF;
}

/* Glassmorphism v2 Sidebar */
section[data-testid="stSidebar"] {
    background: rgba(10, 10, 10, 0.7) !important;
    backdrop-filter: blur(12px);
    border-right: 1px solid rgba(230, 57, 70, 0.2);
}

section[data-testid="stSidebar"] * {
    color: #FFFFFF !important;
}

/* Navigation items */
.stRadio > div {
    gap: 0.5rem;
}

.stRadio label {
    background: transparent;
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 0;
    padding: 0.75rem 1rem;
    transition: all 0.3s ease;
    cursor: pointer;
}

.stRadio label:hover {
    border-color: #E63946;
    background: rgba(230, 57, 70, 0.05);
}

/* Bento Grid Cards */
.metric-card {
    background: rgba(255, 255, 255, 0.02);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 0;
    padding: 1.5rem;
    transition: all 0.3s ease;
    animation: fadeIn 0.5s ease;
}

.metric-card:hover {
    border-color: #E63946;
    transform: translateY(-2px);
}

@keyframes fadeIn {
    from {
        opacity: 0;
        transform: translateY(10px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

/* Streamlit metrics override */
div[data-testid="stMetric"] {
    background: rgba(255, 255, 255, 0.02);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 0;
    padding: 1.5rem;
    transition: all 0.3s ease;
}

div[data-testid="stMetric"]:hover {
    border-color: #E63946;
}

div[data-testid="stMetric"] label {
    color: rgba(255, 255, 255, 0.6) !important;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 1px;
}

div[data-testid="stMetric"] [data-testid="stMetricValue"] {
    color: #FFFFFF !important;
    font-size: 2rem;
    font-weight: 600;
}

/* Ghost Buttons */
.stButton > button {
    background: transparent;
    border: 1px solid #E63946;
    border-radius: 0;
    color: #E63946;
    padding: 0.75rem 2rem;
    transition: all 0.3s ease;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 1px;
}

.stButton > button:hover {
    background: #E63946;
    color: #0A0A0A;
}

/* Input fields - DARK BACKGROUND, WHITE TEXT */
.stTextInput input, .stTextArea textarea, .stSelectbox select, .stNumberInput input {
    background: rgba(0, 0, 0, 0.6) !important;
    border: 2px solid rgba(230, 57, 70, 0.4) !important;
    border-radius: 0 !important;
    color: #FFFFFF !important;
    font-weight: 500 !important;
    transition: all 0.3s ease;
    -webkit-text-fill-color: #FFFFFF !important;
}

.stTextInput input:focus, .stTextArea textarea:focus, .stSelectbox select:focus, .stNumberInput input:focus {
    border-color: #E63946 !important;
    box-shadow: 0 0 0 2px rgba(230, 57, 70, 0.3) !important;
    background: rgba(0, 0, 0, 0.8) !important;
}

/* Force white text in inputs */
input, textarea, select {
    color: #FFFFFF !important;
    -webkit-text-fill-color: #FFFFFF !important;
}

/* Input labels */
.stTextInput label, .stTextArea label, .stSelectbox label, .stNumberInput label {
    color: #FFFFFF !important;
    font-size: 0.85rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.5px !important;
}

/* Selectbox dropdown */
.stSelectbox div[data-baseweb="select"] > div {
    background: rgba(0, 0, 0, 0.6) !important;
    border: 2px solid rgba(230, 57, 70, 0.4) !important;
    color: #FFFFFF !important;
}

/* Selectbox text */
.stSelectbox div[data-baseweb="select"] span {
    color: #FFFFFF !important;
}

/* Selectbox dropdown menu */
.stSelectbox div[role="listbox"] {
    background: rgba(10, 10, 10, 0.98) !important;
    border: 2px solid rgba(230, 57, 70, 0.5) !important;
}

.stSelectbox div[role="option"] {
    color: #FFFFFF !important;
    background: transparent !important;
}

.stSelectbox div[role="option"]:hover {
    background: rgba(230, 57, 70, 0.3) !important;
}

/* Placeholder text */
.stTextInput input::placeholder, .stTextArea textarea::placeholder {
    color: rgba(255, 255, 255, 0.5) !important;
    -webkit-text-fill-color: rgba(255, 255, 255, 0.5) !important;
}

/* Number input specific */
.stNumberInput input[type="number"] {
    color: #FFFFFF !important;
    -webkit-text-fill-color: #FFFFFF !important;
}

/* Expanders */
.streamlit-expanderHeader {
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.2);
    border-radius: 0;
    color: #FFFFFF !important;
    transition: all 0.3s ease;
}

.streamlit-expanderHeader:hover {
    border-color: #E63946;
    background: rgba(230, 57, 70, 0.1);
}

.streamlit-expanderHeader p {
    color: #FFFFFF !important;
}

.streamlit-expanderContent {
    background: rgba(255, 255, 255, 0.02);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-top: none;
    color: #FFFFFF !important;
}

/* Headers */
h1, h2, h3, h4, h5, h6 {
    color: #FFFFFF !important;
    font-weight: 600 !important;
    letter-spacing: -0.5px !important;
}

/* Paragraphs and text */
p, span, div {
    color: #FFFFFF !important;
}

/* Markdown text */
.stMarkdown {
    color: #FFFFFF !important;
}

.stMarkdown p {
    color: #FFFFFF !important;
}

/* Text in general */
.element-container {
    color: #FFFFFF !important;
}

/* Dividers */
hr {
    border-color: rgba(230, 57, 70, 0.2);
}

/* Info/Warning/Error boxes */
.stAlert {
    background: rgba(255, 255, 255, 0.08) !important;
    border: 1px solid rgba(255, 255, 255, 0.3) !important;
    border-radius: 0 !important;
    color: #FFFFFF !important;
}

.stSuccess {
    background: rgba(0, 255, 0, 0.15) !important;
    border-color: rgba(0, 255, 0, 0.5) !important;
    color: #00FF00 !important;
}

.stWarning {
    background: rgba(255, 165, 0, 0.15) !important;
    border-color: rgba(255, 165, 0, 0.5) !important;
    color: #FFA500 !important;
}

.stError {
    background: rgba(230, 57, 70, 0.15) !important;
    border-color: rgba(230, 57, 70, 0.5) !important;
    color: #FF6B6B !important;
}

.stInfo {
    background: rgba(100, 149, 237, 0.15) !important;
    border-color: rgba(100, 149, 237, 0.5) !important;
    color: #6495ED !important;
}

/* Footer */
.footer {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    padding: 10px;
    text-align: center;
    font-size: 10px;
    opacity: 0.5;
    color: #FFFFFF;
    background: rgba(10, 10, 10, 0.9);
    border-top: 1px solid rgba(230, 57, 70, 0.2);
    z-index: 999;
}

/* Slider */
.stSlider > div > div > div {
    background: rgba(255, 255, 255, 0.1);
}

.stSlider > div > div > div > div {
    background: #E63946;
}

/* Code blocks */
code {
    background: rgba(230, 57, 70, 0.15) !important;
    border: 1px solid rgba(230, 57, 70, 0.3) !important;
    border-radius: 0 !important;
    color: #FFFFFF !important;
    padding: 0.2rem 0.4rem;
    font-weight: 500;
}

pre {
    background: rgba(255, 255, 255, 0.05) !important;
    border: 1px solid rgba(255, 255, 255, 0.2) !important;
    border-radius: 0 !important;
    color: #FFFFFF !important;
}

/* Text elements */
.stText {
    color: #FFFFFF !important;
}
</style>
"""


# ============================================================================
# LUCIDE ICONS (SVG)
# ============================================================================

ICONS = {
    "dashboard": '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>',
    "search": '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><path d="m21 21-4.35-4.35"></path></svg>',
    "key": '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="7.5" cy="15.5" r="5.5"></circle><path d="m21 2-9.6 9.6"></path><path d="m15.5 7.5 3 3L22 7l-3-3"></path></svg>',
}


# ============================================================================
# BACKEND FUNCTIONS (PRESERVED FROM ORIGINAL)
# ============================================================================

def load_config() -> dict:
    """Load configuration from config.json."""
    config_path = Path("config.json")
    if not config_path.exists():
        st.error("Configuration file not found: config.json")
        return {}
    
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config: dict) -> None:
    """Save configuration to config.json."""
    with open("config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


async def get_system_stats() -> Tuple[int, int, int, int, int, int]:
    """Get system statistics from database."""
    db_path = Path("telegram_leads.db")
    
    if not db_path.exists():
        return 0, 0, 0, 0, 0, 0
    
    try:
        async with aiosqlite.connect("telegram_leads.db") as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM userbots WHERE status='active'"
            )
            active_userbots = (await cursor.fetchone())[0]
            
            cursor = await db.execute("SELECT COUNT(*) FROM userbots")
            total_userbots = (await cursor.fetchone())[0]
            
            cursor = await db.execute(
                "SELECT COUNT(*) FROM chats WHERE status='active'"
            )
            active_chats = (await cursor.fetchone())[0]
            
            cursor = await db.execute("SELECT COUNT(*) FROM chats")
            total_chats = (await cursor.fetchone())[0]
            
            cursor = await db.execute("""
                SELECT COUNT(*) FROM activity_logs 
                WHERE component='DeliveryBot' 
                AND level='INFO'
                AND message LIKE '%lead delivered%'
                AND DATE(created_at) = DATE('now')
            """)
            leads_today = (await cursor.fetchone())[0]
            
            cursor = await db.execute("""
                SELECT COUNT(*) FROM join_tasks 
                WHERE status='pending'
            """)
            pending_tasks = (await cursor.fetchone())[0]
            
            return active_userbots, total_userbots, active_chats, total_chats, leads_today, pending_tasks
    except Exception as e:
        st.error(f"Error fetching stats: {e}")
        return 0, 0, 0, 0, 0, 0


async def get_recent_activity() -> List[Dict]:
    """Get recent activity logs."""
    db_path = Path("telegram_leads.db")
    
    if not db_path.exists():
        return []
    
    try:
        async with aiosqlite.connect("telegram_leads.db") as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT component, level, message, created_at
                FROM activity_logs
                ORDER BY created_at DESC
                LIMIT 20
            """)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception:
        return []


async def get_userbot_status() -> List[Dict]:
    """Get userbot status information."""
    db_path = Path("telegram_leads.db")
    
    if not db_path.exists():
        return []
    
    try:
        async with aiosqlite.connect("telegram_leads.db") as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT id, session_file, status, joins_today, 
                       unavailable_until, created_at
                FROM userbots
                ORDER BY id
            """)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception:
        return []


async def get_chat_status() -> List[Dict]:
    """Get chat status information."""
    db_path = Path("telegram_leads.db")
    
    if not db_path.exists():
        return []
    
    try:
        async with aiosqlite.connect("telegram_leads.db") as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT id, chat_link, chat_title, status, 
                       assigned_userbot_id, joined_at, error_message
                FROM chats
                ORDER BY created_at DESC
                LIMIT 50
            """)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception:
        return []


# ============================================================================
# MAIN APPLICATION
# ============================================================================

def main():
    """Main dashboard application."""
    st.set_page_config(
        page_title="Be[Sales] Intelligence System",
        page_icon="▪️",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Inject Stealth CSS
    st.markdown(STEALTH_CSS, unsafe_allow_html=True)
    
    # Load configuration
    config = load_config()
    if not config:
        st.stop()
    
    # Sidebar navigation with glassmorphism
    with st.sidebar:
        st.markdown("### BE[SALES] INTELLIGENCE")
        st.markdown("---")
        
        page = st.radio(
            "NAVIGATION",
            [
                "01 // DASHBOARD",
                "02 // CHANNELS",
                "03 // TRIGGERS",
                "04 // ASSETS",
                "05 // LOGS"
            ],
            label_visibility="collapsed"
        )
        
        st.markdown("---")
        st.markdown("**SYSTEM STATUS**")
        st.markdown("```\nOPERATIONAL\n```")
    
    # Route to appropriate page
    if page == "01 // DASHBOARD":
        show_dashboard(config)
    elif page == "02 // CHANNELS":
        show_channels(config)
    elif page == "03 // TRIGGERS":
        show_trigger_words(config)
    elif page == "04 // ASSETS":
        show_api_keys(config)
    elif page == "05 // LOGS":
        show_logs(config)
    
    # Footer
    st.markdown("""
    <div class="footer">
        Be[Sales] // PROPRIETARY INTELLIGENCE SYSTEM. OPERATED BY BE[REC] STUDIOS.
    </div>
    """, unsafe_allow_html=True)


# ============================================================================
# PAGE: DASHBOARD
# ============================================================================

def show_dashboard(config: dict):
    """Show system status dashboard with Bento Grid layout."""
    st.markdown("# 01 // DASHBOARD")
    st.markdown("REAL-TIME SYSTEM METRICS")
    st.markdown("---")
    
    # Refresh button
    col_title, col_refresh = st.columns([5, 1])
    with col_refresh:
        if st.button("REFRESH"):
            st.rerun()
    
    # Get statistics
    stats = asyncio.run(get_system_stats())
    active_userbots, total_userbots, active_chats, total_chats, leads_today, pending_tasks = stats
    
    # Bento Grid - Main metrics
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            "ACTIVE USERBOTS", 
            f"{active_userbots}/{total_userbots}"
        )
    
    with col2:
        st.metric(
            "MONITORED CHATS", 
            f"{active_chats}/{total_chats}"
        )
    
    with col3:
        st.metric(
            "LEADS TODAY", 
            leads_today
        )
    
    st.markdown("---")
    
    # Secondary metrics
    col4, col5, col6 = st.columns(3)
    
    with col4:
        st.metric("QUEUE TASKS", pending_tasks)
    
    with col5:
        spam_count = 0
        try:
            async def get_spam_count():
                async with aiosqlite.connect("telegram_leads.db") as db:
                    cursor = await db.execute("SELECT COUNT(*) FROM spam_database")
                    return (await cursor.fetchone())[0]
            if Path("telegram_leads.db").exists():
                spam_count = asyncio.run(get_spam_count())
        except:
            pass
        st.metric("SPAM SAMPLES", spam_count)
    
    with col6:
        blocked_count = 0
        try:
            async def get_blocked_count():
                async with aiosqlite.connect("telegram_leads.db") as db:
                    cursor = await db.execute("SELECT COUNT(*) FROM blocklist")
                    return (await cursor.fetchone())[0]
            if Path("telegram_leads.db").exists():
                blocked_count = asyncio.run(get_blocked_count())
        except:
            pass
        st.metric("BLOCKED USERS", blocked_count)
    
    # Userbot status
    st.markdown("---")
    st.markdown("### USERBOT STATUS")
    
    userbots = asyncio.run(get_userbot_status())
    if userbots:
        for bot in userbots:
            status_indicator = {
                "active": "ACTIVE",
                "unavailable": "PAUSED",
                "banned": "BANNED",
                "inactive": "OFFLINE"
            }.get(bot["status"], "UNKNOWN")
            
            with st.expander(f"USERBOT #{bot['id']} // {status_indicator}"):
                st.markdown(f"**SESSION:** `{bot['session_file']}`")
                st.markdown(f"**JOINS TODAY:** {bot['joins_today']}")
                if bot['unavailable_until']:
                    st.markdown(f"**UNAVAILABLE UNTIL:** {bot['unavailable_until']}")
                st.markdown(f"**CREATED:** {bot['created_at']}")
    else:
        st.info("NO USERBOTS REGISTERED")
    
    # Chat status
    st.markdown("---")
    st.markdown("### CHAT STATUS")
    
    chats = asyncio.run(get_chat_status())
    if chats:
        for chat in chats:
            status_indicator = {
                "pending": "PENDING",
                "active": "ACTIVE",
                "error": "ERROR",
                "awaiting_approval": "AWAITING",
                "manual_required": "MANUAL"
            }.get(chat["status"], "UNKNOWN")
            
            title = chat["chat_title"] or "UNTITLED"
            with st.expander(f"{title} // {status_indicator}"):
                st.markdown(f"**LINK:** {chat['chat_link']}")
                if chat['assigned_userbot_id']:
                    st.markdown(f"**ASSIGNED:** Userbot #{chat['assigned_userbot_id']}")
                if chat['joined_at']:
                    st.markdown(f"**JOINED:** {chat['joined_at']}")
                if chat['error_message']:
                    st.error(f"**ERROR:** {chat['error_message']}")
    else:
        st.info("NO CHATS REGISTERED")
    
    # Recent activity
    st.markdown("---")
    st.markdown("### ACTIVITY LOG")
    
    activities = asyncio.run(get_recent_activity())
    if activities:
        for activity in activities[:10]:
            level_prefix = {
                "INFO": "INFO",
                "WARNING": "WARN",
                "ERROR": "ERR"
            }.get(activity["level"], "LOG")
            
            timestamp = activity["created_at"]
            st.text(f"[{timestamp}] {level_prefix} // {activity['component']}: {activity['message']}")
    else:
        st.info("NO ACTIVITY LOGGED")


# ============================================================================
# PAGE: CHANNELS
# ============================================================================

def show_channels(config: dict):
    """Show and manage monitored channels."""
    st.markdown("# 02 // CHANNELS")
    st.markdown("CHANNEL MANAGEMENT & MONITORING")
    st.markdown("---")
    
    # Add new channel section
    st.markdown("### ADD NEW CHANNEL")
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        new_channel = st.text_input(
            "CHANNEL LINK",
            placeholder="https://t.me/channel_name or @channel_name",
            help="Enter Telegram channel link or username"
        )
    
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)  # Spacing
        if st.button("ADD CHANNEL", type="primary"):
            if new_channel:
                # Add to database
                async def add_channel():
                    async with aiosqlite.connect("telegram_leads.db") as db:
                        await db.execute("""
                            INSERT INTO chats (chat_link, status)
                            VALUES (?, 'pending')
                        """, (new_channel,))
                        await db.commit()
                
                try:
                    asyncio.run(add_channel())
                    st.success(f"CHANNEL ADDED: {new_channel}")
                    st.rerun()
                except Exception as e:
                    st.error(f"ERROR: {e}")
            else:
                st.warning("ENTER CHANNEL LINK")
    
    st.markdown("---")
    
    # Channel list
    st.markdown("### MONITORED CHANNELS")
    
    chats = asyncio.run(get_chat_status())
    
    if not chats:
        st.info("NO CHANNELS ADDED YET")
        return
    
    # Filter options
    col1, col2, col3 = st.columns(3)
    
    with col1:
        filter_status = st.selectbox(
            "FILTER BY STATUS",
            ["ALL", "PENDING", "ACTIVE", "ERROR", "AWAITING", "MANUAL"]
        )
    
    # Apply filter
    if filter_status != "ALL":
        chats = [c for c in chats if c["status"].upper() == filter_status]
    
    st.markdown(f"**SHOWING {len(chats)} CHANNEL(S)**")
    st.markdown("---")
    
    # Display channels
    for chat in chats:
        status_indicator = {
            "pending": "⏳ PENDING",
            "active": "✓ ACTIVE",
            "error": "✗ ERROR",
            "awaiting_approval": "⏸ AWAITING",
            "manual_required": "⚠ MANUAL"
        }.get(chat["status"], "? UNKNOWN")
        
        title = chat["chat_title"] or "UNTITLED"
        
        with st.expander(f"{title} // {status_indicator}"):
            col1, col2 = st.columns([3, 1])
            
            with col1:
                st.markdown(f"**LINK:** {chat['chat_link']}")
                st.markdown(f"**STATUS:** {chat['status']}")
                
                if chat['assigned_userbot_id']:
                    st.markdown(f"**USERBOT:** #{chat['assigned_userbot_id']}")
                
                if chat['joined_at']:
                    st.markdown(f"**JOINED:** {chat['joined_at']}")
                
                if chat['error_message']:
                    st.error(f"**ERROR:** {chat['error_message']}")
            
            with col2:
                # Delete button
                if st.button(f"DELETE", key=f"del_{chat['id']}"):
                    async def delete_chat():
                        async with aiosqlite.connect("telegram_leads.db") as db:
                            await db.execute("DELETE FROM chats WHERE id = ?", (chat['id'],))
                            await db.commit()
                    
                    try:
                        asyncio.run(delete_chat())
                        st.success("DELETED")
                        st.rerun()
                    except Exception as e:
                        st.error(f"ERROR: {e}")


# ============================================================================
# PAGE: TRIGGERS
# ============================================================================

def show_trigger_words(config: dict):
    """Show and edit trigger words."""
    st.markdown("# 02 // TRIGGERS")
    st.markdown("KEYWORD FILTERING CONFIGURATION")
    st.markdown("---")
    
    st.markdown("""
    Trigger words are used for primary message filtering. 
    Only messages containing at least one trigger word will be sent to LLM verification.
    """)
    
    trigger_words = st.text_area(
        "TRIGGER WORDS (one per line)",
        value="\n".join(config.get("trigger_words", [])),
        height=400
    )
    
    # Word count
    word_list = [word.strip() for word in trigger_words.split("\n") if word.strip()]
    st.markdown(f"**TOTAL KEYWORDS:** {len(word_list)}")
    
    st.markdown("---")
    
    if st.button("SAVE TRIGGERS", type="primary"):
        config["trigger_words"] = word_list
        save_config(config)
        st.success("TRIGGERS SAVED SUCCESSFULLY")
    
    # Display current trigger words as code blocks
    if word_list:
        st.markdown("---")
        st.markdown("### ACTIVE TRIGGERS")
        cols_per_row = 5
        for i in range(0, len(word_list), cols_per_row):
            cols = st.columns(cols_per_row)
            for j, word in enumerate(word_list[i:i+cols_per_row]):
                with cols[j]:
                    st.markdown(f"`{word}`")


# ============================================================================
# PAGE: ASSETS (API Keys + Queue Settings)
# ============================================================================

def show_api_keys(config: dict):
    """Show and edit API keys and system settings."""
    st.markdown("# 03 // ASSETS")
    st.markdown("API CREDENTIALS & SYSTEM CONFIGURATION")
    st.markdown("---")
    
    # LLM Configuration
    st.markdown("### LLM CONFIGURATION")
    
    provider_options = ["claude", "openai", "openrouter"]
    current_provider = config.get("llm_provider", "claude")
    provider_index = provider_options.index(current_provider) if current_provider in provider_options else 0
    
    config["llm_provider"] = st.selectbox(
        "LLM PROVIDER",
        provider_options,
        index=provider_index
    )
    
    config["llm_api_key"] = st.text_input(
        "LLM API KEY",
        value=config.get("llm_api_key", ""),
        type="password"
    )
    
    # Model selection (optional)
    model_help = {
        "claude": "Default: claude-3-haiku-20240307",
        "openai": "Default: gpt-4o-mini",
        "openrouter": "Default: anthropic/claude-3.5-haiku. Examples: google/gemini-2.0-flash-exp, meta-llama/llama-3.3-70b-instruct"
    }
    
    config["llm_model"] = st.text_input(
        "MODEL NAME (OPTIONAL)",
        value=config.get("llm_model", ""),
        help=model_help.get(config["llm_provider"], "Leave empty for default model")
    )
    
    if config.get("llm_api_key"):
        st.success("API KEY CONFIGURED")
    else:
        st.warning("API KEY NOT SET")
    
    st.markdown("---")
    
    # Telegram Configuration
    st.markdown("### TELEGRAM CONFIGURATION")
    
    config["telegram_api_id"] = st.text_input(
        "TELEGRAM API ID",
        value=config.get("telegram_api_id", ""),
        help="Get from https://my.telegram.org/apps"
    )
    
    config["telegram_api_hash"] = st.text_input(
        "TELEGRAM API HASH",
        value=config.get("telegram_api_hash", ""),
        type="password",
        help="Get from https://my.telegram.org/apps"
    )
    
    config["bot_token"] = st.text_input(
        "BOT TOKEN",
        value=config.get("bot_token", ""),
        type="password",
        help="Get from @BotFather"
    )
    
    config["operator_chat_id"] = st.text_input(
        "OPERATOR CHAT ID",
        value=config.get("operator_chat_id", ""),
        help="Get from @userinfobot"
    )
    
    # Configuration status
    st.markdown("---")
    st.markdown("### CONFIGURATION STATUS")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**TELEGRAM API:**")
        if config.get("telegram_api_id") and config.get("telegram_api_hash"):
            st.success("CONFIGURED")
        else:
            st.error("NOT CONFIGURED")
    
    with col2:
        st.markdown("**BOT CONFIG:**")
        if config.get("bot_token") and config.get("operator_chat_id"):
            st.success("CONFIGURED")
        else:
            st.error("NOT CONFIGURED")
    
    st.markdown("---")
    st.markdown("---")
    
    # Queue Settings
    st.markdown("### QUEUE SETTINGS")
    
    min_delay, max_delay = st.slider(
        "JOIN DELAY RANGE (seconds)",
        min_value=60,
        max_value=3600,
        value=(
            config.get("join_delay_min", 300),
            config.get("join_delay_max", 1800)
        )
    )
    config["join_delay_min"] = min_delay
    config["join_delay_max"] = max_delay
    
    col1, col2 = st.columns(2)
    with col1:
        st.info(f"MIN: {min_delay // 60}m {min_delay % 60}s")
    with col2:
        st.info(f"MAX: {max_delay // 60}m {max_delay % 60}s")
    
    config["daily_join_limit"] = st.number_input(
        "DAILY JOIN LIMIT (per userbot)",
        min_value=1,
        max_value=50,
        value=config.get("daily_join_limit", 10)
    )
    
    st.info(f"MONTHLY CAPACITY: ~{config['daily_join_limit'] * 30} chats/userbot")
    
    st.markdown("---")
    
    # LLM Settings
    st.markdown("### LLM SETTINGS")
    
    config["llm_max_concurrent"] = st.number_input(
        "MAX CONCURRENT REQUESTS",
        min_value=1,
        max_value=50,
        value=config.get("llm_max_concurrent", 10)
    )
    
    config["llm_timeout"] = st.number_input(
        "REQUEST TIMEOUT (seconds)",
        min_value=5,
        max_value=120,
        value=config.get("llm_timeout", 30)
    )
    
    config["llm_max_retries"] = st.number_input(
        "MAX RETRIES",
        min_value=1,
        max_value=10,
        value=config.get("llm_max_retries", 3)
    )
    
    st.markdown("---")
    
    # Advanced Settings
    st.markdown("### ADVANCED SETTINGS")
    
    config["health_check_interval"] = st.number_input(
        "HEALTH CHECK INTERVAL (seconds)",
        min_value=60,
        max_value=3600,
        value=config.get("health_check_interval", 300)
    )
    
    config["spam_cache_update_interval"] = st.number_input(
        "SPAM CACHE UPDATE (seconds)",
        min_value=10,
        max_value=600,
        value=config.get("spam_cache_update_interval", 60)
    )
    
    config["max_spam_examples"] = st.number_input(
        "MAX SPAM EXAMPLES",
        min_value=5,
        max_value=50,
        value=config.get("max_spam_examples", 20)
    )
    
    st.markdown("---")
    
    if st.button("SAVE CONFIGURATION", type="primary"):
        save_config(config)
        st.success("CONFIGURATION SAVED")


# ============================================================================
# PAGE: LOGS
# ============================================================================

def show_logs(config: dict):
    """Show system logs and banned userbots."""
    st.markdown("# 05 // LOGS")
    st.markdown("SYSTEM LOGS & BANNED ACCOUNTS")
    st.markdown("---")
    
    # Tabs for different log views
    tab1, tab2 = st.tabs(["ACTIVITY LOGS", "BANNED USERBOTS"])
    
    with tab1:
        st.markdown("### ACTIVITY LOGS")
        
        # Filter options
        col1, col2, col3 = st.columns(3)
        
        with col1:
            log_level = st.selectbox(
                "LOG LEVEL",
                ["ALL", "INFO", "WARNING", "ERROR"]
            )
        
        with col2:
            log_component = st.selectbox(
                "COMPONENT",
                ["ALL", "JoinLogic", "DeliveryBot", "LLMVerifier", "MessageParser", "IngestionModule"]
            )
        
        with col3:
            log_limit = st.number_input(
                "LIMIT",
                min_value=10,
                max_value=500,
                value=100,
                step=10
            )
        
        # Fetch logs
        async def get_filtered_logs():
            db_path = Path("telegram_leads.db")
            if not db_path.exists():
                return []
            
            query = "SELECT component, level, message, created_at FROM activity_logs WHERE 1=1"
            params = []
            
            if log_level != "ALL":
                query += " AND level = ?"
                params.append(log_level)
            
            if log_component != "ALL":
                query += " AND component = ?"
                params.append(log_component)
            
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(log_limit)
            
            async with aiosqlite.connect("telegram_leads.db") as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(query, params)
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
        
        logs = asyncio.run(get_filtered_logs())
        
        if logs:
            st.markdown(f"**SHOWING {len(logs)} LOG ENTRIES**")
            st.markdown("---")
            
            for log in logs:
                level_color = {
                    "INFO": "🟢",
                    "WARNING": "🟡",
                    "ERROR": "🔴"
                }.get(log["level"], "⚪")
                
                with st.expander(f"{level_color} [{log['created_at']}] {log['component']}"):
                    st.markdown(f"**LEVEL:** {log['level']}")
                    st.markdown(f"**COMPONENT:** {log['component']}")
                    st.markdown(f"**MESSAGE:**")
                    st.code(log['message'])
        else:
            st.info("NO LOGS FOUND")
    
    with tab2:
        st.markdown("### BANNED USERBOTS")
        
        # Fetch banned userbots
        async def get_banned_userbots():
            db_path = Path("telegram_leads.db")
            if not db_path.exists():
                return []
            
            async with aiosqlite.connect("telegram_leads.db") as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute("""
                    SELECT id, session_file, created_at, updated_at
                    FROM userbots
                    WHERE status = 'banned'
                    ORDER BY updated_at DESC
                """)
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
        
        banned = asyncio.run(get_banned_userbots())
        
        if banned:
            st.markdown(f"**FOUND {len(banned)} BANNED USERBOT(S)**")
            st.markdown("---")
            
            for bot in banned:
                with st.expander(f"🚫 USERBOT #{bot['id']} // {bot['session_file']}"):
                    col1, col2 = st.columns([3, 1])
                    
                    with col1:
                        st.markdown(f"**ID:** {bot['id']}")
                        st.markdown(f"**SESSION:** {bot['session_file']}")
                        st.markdown(f"**CREATED:** {bot['created_at']}")
                        st.markdown(f"**BANNED:** {bot['updated_at']}")
                    
                    with col2:
                        if st.button(f"DELETE", key=f"del_banned_{bot['id']}"):
                            async def delete_banned():
                                async with aiosqlite.connect("telegram_leads.db") as db:
                                    await db.execute("DELETE FROM userbots WHERE id = ?", (bot['id'],))
                                    await db.commit()
                            
                            try:
                                asyncio.run(delete_banned())
                                st.success("DELETED")
                                st.rerun()
                            except Exception as e:
                                st.error(f"ERROR: {e}")
        else:
            st.success("NO BANNED USERBOTS")
        
        st.markdown("---")
        
        # Bulk delete button
        if banned:
            if st.button("DELETE ALL BANNED USERBOTS", type="primary"):
                async def delete_all_banned():
                    async with aiosqlite.connect("telegram_leads.db") as db:
                        await db.execute("DELETE FROM userbots WHERE status = 'banned'")
                        await db.commit()
                
                try:
                    asyncio.run(delete_all_banned())
                    st.success(f"DELETED {len(banned)} BANNED USERBOT(S)")
                    st.rerun()
                except Exception as e:
                    st.error(f"ERROR: {e}")


if __name__ == "__main__":
    main()
