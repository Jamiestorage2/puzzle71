#!/usr/bin/env python3
"""
KeyHunt Smart Coordinator v3.5.0
=================================
Enhanced KeyHunt GUI with:
- Hourly pool scraping (btcpuzzle.info)
- Challenge tracking (✅7FXXXXX patterns)
- Local scan tracking
- Block-based searching
- Pause/Resume with state persistence
- Automatic exclusion management
- Fixed pool data persistence
- Fixed visualization overlaps
- Fixed percentage calculations

Version: 3.0.1
Build Date: 2026-01-03
Changes:
- v3.5.0: Fixed visualization (blue/green bars show overlaps, correct percentages)
- v3.0.0: Fixed pool data persistence on restart + challenge tracking
- v2.0.0: Added correct pool padding (3000000000) + challenges
"""

__version__ = "3.5.0"
__build_date__ = "2026-01-03"
__build_name__ = "Block Manager - Delete Auto-Stop + Alert on Match Rescan"

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Pango, Gdk
import cairo
import subprocess
import threading
import os
import re
import json
import sqlite3
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from pathlib import Path

class PoolScraper:
    """Scrapes btcpuzzle.info for already-scanned ranges"""
    
    def __init__(self, puzzle_number=71):
        self.puzzle_number = puzzle_number
        self.update_puzzle(puzzle_number)
    
    def update_puzzle(self, puzzle_number):
        """Update to different puzzle"""
        self.puzzle_number = puzzle_number
        self.base_url = f"https://btcpuzzle.info/puzzle/{puzzle_number}"
        
    def scrape_scanned_ranges(self):
        """Scrape currently scanned ranges from pool"""
        try:
            print(f"\n{'='*80}")
            print(f"🌐 POOL SCRAPER - LIVE DATA FETCH")
            print(f"{'='*80}")
            print(f"📍 URL: {self.base_url}")
            print(f"⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"🔍 Fetching data from btcpuzzle.info...")
            
            response = requests.get(self.base_url, timeout=30)
            response.raise_for_status()
            
            print(f"✅ HTTP Status: {response.status_code}")
            print(f"📦 Response Size: {len(response.text):,} bytes")
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract range IDs (format: 50XA1EC - 4 to 5 hex digits after X)
            # NOTE: Pool format uses 4-5 chars, not 6! Matching 6 picks up extra digits.
            range_pattern = re.compile(r'[0-9A-F]{2}X[0-9A-F]{4,5}')
            text_content = soup.get_text()
            matches = range_pattern.findall(text_content)
            
            print(f"🔢 Found {len(matches)} total range IDs (including duplicates)")
            unique_ranges = set(matches)
            print(f"🎯 Unique range IDs: {len(unique_ranges)}")
            
            # Extract completed challenges (✅7FXXXXX format)
            challenge_pattern = re.compile(r'✅([0-9A-F]{2})XXXXX')
            challenge_matches = challenge_pattern.findall(text_content)
            unique_challenges = set(challenge_matches)
            
            if unique_challenges:
                print(f"\n🏆 Found {len(unique_challenges)} completed challenges")
                print(f"   Challenges: {', '.join(sorted(unique_challenges))}")
            
            # Show first 10 examples
            print(f"\n📋 Example Range IDs from website:")
            for i, range_id in enumerate(sorted(unique_ranges)[:10]):
                print(f"   {i+1}. {range_id}")
            if len(unique_ranges) > 10:
                print(f"   ... and {len(unique_ranges) - 10} more")
            
            scanned_blocks = []
            
            # Decode regular ranges
            for range_id in unique_ranges:
                blocks = self._decode_range_id(range_id)
                scanned_blocks.extend(blocks)
            
            # Decode challenges  
            for challenge_prefix in unique_challenges:
                blocks = self._decode_challenge(challenge_prefix)
                scanned_blocks.extend(blocks)
            
            print(f"\n🔢 Total blocks after expansion: {len(scanned_blocks)}")
            print(f"   Regular ranges: {len(unique_ranges)} IDs × 16 = {len(unique_ranges) * 16} blocks")
            print(f"   Challenges: {len(unique_challenges)} × 256 = {len(unique_challenges) * 256} blocks")
            
            # Show first few expanded blocks
            print(f"\n📊 Example Expanded Blocks:")
            for i, (start, end) in enumerate(scanned_blocks[:5]):
                print(f"   {i+1}. 0x{start:X} → 0x{end:X}")
            if len(scanned_blocks) > 5:
                print(f"   ... and {len(scanned_blocks) - 5} more")
            
            print(f"{'='*80}\n")
            
            return scanned_blocks
            
        except Exception as e:
            print(f"❌ Pool scrape error: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _decode_range_id(self, range_id):
        """Decode pool range ID to actual hex blocks
        
        Format: PP X SSSS or PP X SSSSS
        Example: 50 X A1EC (4-char suffix)
        Example: 41 X A26C0 (5-char suffix)
        
        Expands to: PP + [0-F] + SUFFIX + 3000000000
        Result: 18 hex digits total
        """
        # Remove X and expand
        hex_prefix = range_id[0:2]
        hex_suffix = range_id[3:]  # Will be 4 or 5 chars
        
        blocks = []
        for x in '0123456789ABCDEF':
            # Format: PP + X + SUFFIX + 3000000000 = 18 chars
            block_start = int(hex_prefix + x + hex_suffix + '3000000000', 16)
            block_end = int(hex_prefix + x + hex_suffix + '3FFFFFFFFF', 16)
            blocks.append((block_start, block_end))
        
        return blocks
    
    def _decode_challenge(self, challenge_prefix):
        """Decode completed challenge (e.g., 7F → all 7F????? ranges)
        
        A challenge like "7FXXXXX" covers ALL ranges starting with 7F.
        We expand this to 256 blocks (16×16) to cover the space efficiently.
        """
        blocks = []
        
        # Expand 7FXXXXX to 7F00XXX, 7F01XXX, ... 7FFFXXX
        for x1 in '0123456789ABCDEF':
            for x2 in '0123456789ABCDEF':
                # Format: 7F + 00 + 000 + 3000000000
                block_start = int(challenge_prefix + x1 + x2 + '0003000000000', 16)
                block_end = int(challenge_prefix + x1 + x2 + '0003FFFFFFFFF', 16)
                blocks.append((block_start, block_end))
        
        return blocks


class BlockManager:
    """Manages keyspace blocks for systematic searching"""
    
    def __init__(self, range_start, range_end, block_size=None):
        self.range_start = range_start
        self.range_end = range_end
        
        # Auto-calculate block size (match pool's ~35 trillion)
        if block_size is None:
            self.block_size = 0x1000000000  # ~68 billion keys per block
        else:
            self.block_size = block_size
        
        self.total_blocks = (range_end - range_start) // self.block_size + 1
        
    def get_block(self, block_index):
        """Get start/end for a specific block"""
        block_start = self.range_start + (block_index * self.block_size)
        block_end = min(block_start + self.block_size - 1, self.range_end)
        return (block_start, block_end)
    
    def get_block_from_key(self, key_value):
        """Find which block a key belongs to"""
        if key_value < self.range_start or key_value > self.range_end:
            return None
        block_index = (key_value - self.range_start) // self.block_size
        return block_index


class ScanDatabase:
    """SQLite database for tracking scanned blocks"""
    
    def __init__(self, puzzle_number=71):
        self.puzzle_number = puzzle_number
        self.db_path = f"scan_data_puzzle_{puzzle_number}.db"
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._create_tables()
    
    def switch_puzzle(self, puzzle_number):
        """Switch to a different puzzle database"""
        # Close current connection
        self.conn.close()
        
        # Open new database for new puzzle
        self.puzzle_number = puzzle_number
        self.db_path = f"scan_data_puzzle_{puzzle_number}.db"
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._create_tables()
    
    def _create_tables(self):
        """Create database tables"""
        cursor = self.conn.cursor()
        
        # Pool scanned blocks (store as TEXT hex to avoid integer overflow)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pool_scanned (
                block_start TEXT PRIMARY KEY,
                block_end TEXT,
                scraped_at TEXT
            )
        ''')
        
        # My scanned blocks (store as TEXT hex to avoid integer overflow)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS my_scanned (
                block_start TEXT PRIMARY KEY,
                block_end TEXT,
                scanned_at TEXT,
                keys_checked INTEGER
            )
        ''')
        
        self.conn.commit()
    
    def add_pool_blocks(self, blocks):
        """Add pool-scanned blocks and return count of new blocks added"""
        cursor = self.conn.cursor()
        timestamp = datetime.now().isoformat()
        
        added_count = 0
        duplicate_count = 0
        
        for block_start, block_end in blocks:
            # Convert to hex strings for storage
            block_start_hex = hex(block_start)[2:].upper()  # Remove '0x' prefix
            block_end_hex = hex(block_end)[2:].upper()
            
            # Check if block already exists
            cursor.execute('''
                SELECT COUNT(*) FROM pool_scanned 
                WHERE block_start = ?
            ''', (block_start_hex,))
            exists = cursor.fetchone()[0] > 0
            
            if exists:
                duplicate_count += 1
            else:
                added_count += 1
            
            cursor.execute('''
                INSERT OR REPLACE INTO pool_scanned 
                (block_start, block_end, scraped_at)
                VALUES (?, ?, ?)
            ''', (block_start_hex, block_end_hex, timestamp))
        
        self.conn.commit()
        return added_count, duplicate_count
    
    def add_my_block(self, block_start, block_end, keys_checked):
        """Add my scanned block"""
        cursor = self.conn.cursor()
        timestamp = datetime.now().isoformat()
        
        # Convert to hex strings for storage
        block_start_hex = hex(block_start)[2:].upper()
        block_end_hex = hex(block_end)[2:].upper()
        
        cursor.execute('''
            INSERT OR REPLACE INTO my_scanned 
            (block_start, block_end, scanned_at, keys_checked)
            VALUES (?, ?, ?, ?)
        ''', (block_start_hex, block_end_hex, timestamp, keys_checked))
        
        self.conn.commit()
    
    def is_block_scanned(self, block_start, block_end):
        """Check if block already scanned (by pool or me)"""
        cursor = self.conn.cursor()
        
        # Convert to hex strings for comparison
        block_start_hex = hex(block_start)[2:].upper()
        block_end_hex = hex(block_end)[2:].upper()
        
        # Check pool
        cursor.execute('''
            SELECT COUNT(*) FROM pool_scanned 
            WHERE block_start = ? AND block_end = ?
        ''', (block_start_hex, block_end_hex))
        
        if cursor.fetchone()[0] > 0:
            return True, "pool"
        
        # Check my scans
        cursor.execute('''
            SELECT COUNT(*) FROM my_scanned 
            WHERE block_start = ? AND block_end = ?
        ''', (block_start_hex, block_end_hex))
        
        if cursor.fetchone()[0] > 0:
            return True, "me"
        
        return False, None
    
    def get_stats(self):
        """Get scanning statistics"""
        cursor = self.conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM pool_scanned')
        pool_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM my_scanned')
        my_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT SUM(keys_checked) FROM my_scanned')
        total_keys = cursor.fetchone()[0] or 0
        
        return {
            'pool_blocks': pool_count,
            'my_blocks': my_count,
            'total_blocks': pool_count + my_count,
            'total_keys_by_me': total_keys
        }
    
    def close(self):
        """Close database connection"""
        self.conn.close()


class StateManager:
    """Manages pause/resume state"""
    
    def __init__(self, puzzle_number=71):
        self.puzzle_number = puzzle_number
        self.state_file = f"keyhunt_state_puzzle_{puzzle_number}.json"
    
    def switch_puzzle(self, puzzle_number):
        """Switch to a different puzzle state file"""
        self.puzzle_number = puzzle_number
        self.state_file = f"keyhunt_state_puzzle_{puzzle_number}.json"
    
    def save_state(self, state_data):
        """Save current state to file"""
        try:
            # Add puzzle number to state
            state_data['puzzle_number'] = self.puzzle_number
            with open(self.state_file, 'w') as f:
                json.dump(state_data, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving state: {e}")
            return False
    
    def load_state(self):
        """Load state from file"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading state: {e}")
        return None
    
    def clear_state(self):
        """Clear saved state"""
        try:
            if os.path.exists(self.state_file):
                os.remove(self.state_file)
        except:
            pass


class KeyHuntSmartGUI(Gtk.Window):
    
    # Puzzle presets with known information
    PUZZLE_PRESETS = {
        71: {
            'name': 'Puzzle #71',
            'address': '1PWo3JeB9jrGwfHDNpdGK54CRas7fsVzXU',
            'range_start': '400000000000000000',
            'range_end': '7FFFFFFFFFFFFFFFFF',
            'bits': 71,
            'reward': '7.1 BTC'
        },
        72: {
            'name': 'Puzzle #72',
            'address': '1JTK7s9YVYywfm5XUH7RNhHJH1LshCaRFR',
            'range_start': '800000000000000000',
            'range_end': 'FFFFFFFFFFFFFFFFFFF',
            'bits': 72,
            'reward': '7.2 BTC'
        },
        73: {
            'name': 'Puzzle #73',
            'address': '12VVRNPi4SJqUTsp6FmqDqY5sGosDtysn4',
            'range_start': '1000000000000000000',
            'range_end': '1FFFFFFFFFFFFFFFFFFFE',
            'bits': 73,
            'reward': '7.3 BTC'
        },
        74: {
            'name': 'Puzzle #74',
            'address': '1FWGcVDK3JGzCC3WtkYetULPszMaK2Jksv',
            'range_start': '2000000000000000000',
            'range_end': '3FFFFFFFFFFFFFFFFFFFE',
            'bits': 74,
            'reward': '7.4 BTC'
        },
        75: {
            'name': 'Puzzle #75',
            'address': '1DJh2eHFYQfACPmrvpyWc8MSTYKh7w9eRF',
            'range_start': '4000000000000000000',
            'range_end': '7FFFFFFFFFFFFFFFFFFFE',
            'bits': 75,
            'reward': '7.5 BTC'
        }
    }
    
    def __init__(self):
        super().__init__(title=f"KeyHunt Smart Coordinator v{__version__}")
        self.set_default_size(1400, 750)  # Width: 1400, Height: 750 (fits on 1080p screens with scrolling)
        self.set_resizable(True)  # Make window resizable
        self.set_border_width(10)
        
        # Current puzzle
        self.current_puzzle = 71
        
        # Core components
        self.pool_scraper = PoolScraper(puzzle_number=self.current_puzzle)
        self.scan_db = ScanDatabase(puzzle_number=self.current_puzzle)
        self.state_mgr = StateManager(puzzle_number=self.current_puzzle)
        self.block_mgr = None
        
        # State
        self.process = None
        self.is_running = False
        self.is_paused = False
        self.start_time = None
        self.keys_checked = 0  # Total keys checked in this block (including previous sessions)
        self.session_keys = 0  # Keys checked in current session only
        self.matches_found = 0
        self.current_speed = 0
        self.current_block = None
        self.current_block_index = 0
        
        # CACHE: Store blocks to avoid constant DB queries on every redraw
        self.cached_pool_blocks = []
        self.cached_my_blocks = []
        self.cache_dirty = True  # Flag to refresh cache
        
        # Thread safety - prevent starting multiple searches
        self.search_lock = threading.Lock()
        
        # Range tracking
        self.range_start_value = 0
        self.range_end_value = 0
        self.total_keys_in_range = 0
        
        # Pool scraping
        self.last_pool_scrape = None
        self.scrape_interval = 60  # 1 hour in seconds
        
        # Load CSS
        self.apply_css()
        
        # Build UI
        self.build_ui()
        
        # Load previous state if exists
        self.load_previous_state()
        
        # Show pool data stats on startup
        pool_count = len(self.scan_db.conn.execute('SELECT * FROM pool_scanned').fetchall())
        my_count = len(self.scan_db.conn.execute('SELECT * FROM my_scanned').fetchall())
        if pool_count > 0 or my_count > 0:
            self.log("=" * 60, "info")
            self.log("📊 DATABASE LOADED", "success")
            self.log("=" * 60, "info")
            self.log(f"   Pool blocks: {pool_count:,}", "info")
            self.log(f"   My blocks: {my_count:,}", "info")
            self.log("=" * 60, "info")
        
        # Start pool scraper thread (will add new blocks to existing database)
        self.start_pool_scraper()
        
        # Handle window close
        self.connect("delete-event", self.on_window_close)
    
    def build_ui(self):
        """Build the user interface"""
        # Create scrolled window for main content
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)  # No horizontal scroll, automatic vertical
        scrolled_window.set_min_content_height(600)  # Minimum visible height
        self.add(scrolled_window)
        
        # Main content box (inside scrolled window)
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        scrolled_window.add(main_box)
        
        # Header
        header = self.create_header()
        main_box.pack_start(header, False, False, 0)
        
        # Status bar
        status_bar = self.create_status_bar()
        main_box.pack_start(status_bar, False, False, 0)
        
        # Smart coordinator status
        smart_status = self.create_smart_status()
        main_box.pack_start(smart_status, False, False, 0)
        
        # Current block progress bar
        current_block_progress = self.create_current_block_progress()
        main_box.pack_start(current_block_progress, False, False, 0)
        
        # Visual keyspace progress bar
        visual_progress = self.create_visual_progress_bar()
        main_box.pack_start(visual_progress, False, False, 0)
        
        # Probability Dashboard
        probability_dashboard = self.create_probability_dashboard()
        main_box.pack_start(probability_dashboard, False, False, 0)
        
        # Notebook
        notebook = Gtk.Notebook()
        main_box.pack_start(notebook, True, True, 0)
        
        # Tabs
        notebook.append_page(self.create_config_page(), Gtk.Label(label="Configuration"))
        notebook.append_page(self.create_console_page(), Gtk.Label(label="Console"))
        notebook.append_page(self.create_blocks_page(), Gtk.Label(label="Block Manager"))
        notebook.append_page(self.create_exclusions_page(), Gtk.Label(label="Exclusions"))
        notebook.append_page(self.create_manual_input_page(), Gtk.Label(label="Manual Input"))
        
        # Control buttons
        controls = self.create_controls()
        main_box.pack_start(controls, False, False, 0)
    
    def create_header(self):
        """Create header"""
        header_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        
        title = Gtk.Label(label="⚡ KEYHUNT SMART COORDINATOR")
        title.set_markup("<span size='x-large' weight='bold'>⚡ KEYHUNT SMART COORDINATOR</span>")
        header_box.pack_start(title, False, False, 0)
        
        subtitle = Gtk.Label(label="Intelligent Pool-Aware Bitcoin Address Hunter")
        header_box.pack_start(subtitle, False, False, 0)
        
        return header_box
    
    def create_status_bar(self):
        """Create main status bar"""
        frame = Gtk.Frame(label="Live Stats")
        grid = Gtk.Grid()
        grid.set_column_homogeneous(True)
        grid.set_column_spacing(15)
        grid.set_row_spacing(5)
        grid.set_margin_start(10)
        grid.set_margin_end(10)
        grid.set_margin_top(10)
        grid.set_margin_bottom(10)
        frame.add(grid)
        
        # Speed
        grid.attach(Gtk.Label(label="Speed:", xalign=0), 0, 0, 1, 1)
        self.speed_value = Gtk.Label(label="0 Mk/s", xalign=0)
        grid.attach(self.speed_value, 0, 1, 1, 1)
        
        # Keys Checked
        grid.attach(Gtk.Label(label="Keys Checked:", xalign=0), 1, 0, 1, 1)
        self.keys_value = Gtk.Label(label="0", xalign=0)
        grid.attach(self.keys_value, 1, 1, 1, 1)
        
        # Progress
        grid.attach(Gtk.Label(label="Progress:", xalign=0), 2, 0, 1, 1)
        self.progress_value = Gtk.Label(label="0.000000%", xalign=0)
        grid.attach(self.progress_value, 2, 1, 1, 1)
        
        # Runtime
        grid.attach(Gtk.Label(label="Runtime:", xalign=0), 3, 0, 1, 1)
        self.runtime_value = Gtk.Label(label="00:00:00", xalign=0)
        grid.attach(self.runtime_value, 3, 1, 1, 1)
        
        # Matches
        grid.attach(Gtk.Label(label="Matches:", xalign=0), 4, 0, 1, 1)
        self.matches_value = Gtk.Label(label="0", xalign=0)
        grid.attach(self.matches_value, 4, 1, 1, 1)
        
        return frame
    
    def create_smart_status(self):
        """Create smart coordinator status display"""
        frame = Gtk.Frame(label="Smart Coordinator Status")
        grid = Gtk.Grid()
        grid.set_column_homogeneous(True)
        grid.set_column_spacing(15)
        grid.set_row_spacing(5)
        grid.set_margin_start(10)
        grid.set_margin_end(10)
        grid.set_margin_top(10)
        grid.set_margin_bottom(10)
        frame.add(grid)
        
        # Current Block
        grid.attach(Gtk.Label(label="Current Block:", xalign=0), 0, 0, 1, 1)
        self.block_value = Gtk.Label(label="None", xalign=0)
        grid.attach(self.block_value, 0, 1, 1, 1)
        
        # Pool Blocks Excluded
        grid.attach(Gtk.Label(label="Pool Exclusions:", xalign=0), 1, 0, 1, 1)
        self.pool_exclusions_value = Gtk.Label(label="0 blocks", xalign=0)
        grid.attach(self.pool_exclusions_value, 1, 1, 1, 1)
        
        # My Blocks Completed
        grid.attach(Gtk.Label(label="My Completed:", xalign=0), 2, 0, 1, 1)
        self.my_blocks_value = Gtk.Label(label="0 blocks", xalign=0)
        grid.attach(self.my_blocks_value, 2, 1, 1, 1)
        
        # Last Pool Scrape
        grid.attach(Gtk.Label(label="Last Scrape:", xalign=0), 3, 0, 1, 1)
        self.last_scrape_value = Gtk.Label(label="Never", xalign=0)
        grid.attach(self.last_scrape_value, 3, 1, 1, 1)
        
        # Next Scrape
        grid.attach(Gtk.Label(label="Next Scrape:", xalign=0), 4, 0, 1, 1)
        self.next_scrape_value = Gtk.Label(label="--:--:--", xalign=0)
        grid.attach(self.next_scrape_value, 4, 1, 1, 1)
        
        return frame
    
    def create_current_block_progress(self):
        """Create current block progress bar"""
        frame = Gtk.Frame(label="📦 Current Block Progress")
        
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        vbox.set_margin_start(10)
        vbox.set_margin_end(10)
        vbox.set_margin_top(10)
        vbox.set_margin_bottom(10)
        
        # Progress bar
        self.current_block_progressbar = Gtk.ProgressBar()
        self.current_block_progressbar.set_show_text(True)
        self.current_block_progressbar.set_text("0.00%")
        vbox.pack_start(self.current_block_progressbar, False, False, 0)
        
        # Stats label
        self.current_block_stats = Gtk.Label()
        self.current_block_stats.set_markup("<span size='small'>No block active</span>")
        self.current_block_stats.set_halign(Gtk.Align.CENTER)
        vbox.pack_start(self.current_block_stats, False, False, 0)
        
        frame.add(vbox)
        return frame
    
    def create_visual_progress_bar(self):
        """Create visual keyspace progress bar"""
        frame = Gtk.Frame(label="Keyspace Coverage (0-100%)")
        
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        vbox.set_margin_start(10)
        vbox.set_margin_end(10)
        vbox.set_margin_top(10)
        vbox.set_margin_bottom(10)
        
        # Drawing area for progress bar
        self.progress_drawing = Gtk.DrawingArea()
        self.progress_drawing.set_size_request(-1, 60)
        self.progress_drawing.connect("draw", self.on_draw_progress_bar)
        vbox.pack_start(self.progress_drawing, True, True, 0)
        
        # Legend
        legend_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        legend_box.set_halign(Gtk.Align.CENTER)
        
        # Pool scanned (blue)
        pool_legend = Gtk.Box(spacing=5)
        pool_color = Gtk.DrawingArea()
        pool_color.set_size_request(20, 20)
        pool_color.connect("draw", lambda w, cr: self.draw_color_box(cr, 0.2, 0.6, 1.0))
        pool_legend.pack_start(pool_color, False, False, 0)
        pool_legend.pack_start(Gtk.Label(label="Pool Scanned"), False, False, 0)
        legend_box.pack_start(pool_legend, False, False, 0)
        
        # My scanned (green)
        my_legend = Gtk.Box(spacing=5)
        my_color = Gtk.DrawingArea()
        my_color.set_size_request(20, 20)
        my_color.connect("draw", lambda w, cr: self.draw_color_box(cr, 0.3, 0.8, 0.3))
        my_legend.pack_start(my_color, False, False, 0)
        my_legend.pack_start(Gtk.Label(label="My Scanned"), False, False, 0)
        legend_box.pack_start(my_legend, False, False, 0)
        
        # Currently scanning (yellow)
        current_legend = Gtk.Box(spacing=5)
        current_color = Gtk.DrawingArea()
        current_color.set_size_request(20, 20)
        current_color.connect("draw", lambda w, cr: self.draw_color_box(cr, 1.0, 0.8, 0.2))
        current_legend.pack_start(current_color, False, False, 0)
        current_legend.pack_start(Gtk.Label(label="Currently Scanning"), False, False, 0)
        legend_box.pack_start(current_legend, False, False, 0)
        
        # Unscanned (grey)
        unscanned_legend = Gtk.Box(spacing=5)
        unscanned_color = Gtk.DrawingArea()
        unscanned_color.set_size_request(20, 20)
        unscanned_color.connect("draw", lambda w, cr: self.draw_color_box(cr, 0.3, 0.3, 0.3))
        unscanned_legend.pack_start(unscanned_color, False, False, 0)
        unscanned_legend.pack_start(Gtk.Label(label="Unscanned"), False, False, 0)
        legend_box.pack_start(unscanned_legend, False, False, 0)
        
        vbox.pack_start(legend_box, False, False, 0)
        
        # View mode selector
        view_mode_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        view_mode_box.set_halign(Gtk.Align.CENTER)
        view_mode_box.set_margin_top(5)
        
        view_label = Gtk.Label(label="View:")
        view_mode_box.pack_start(view_label, False, False, 0)
        
        # View mode buttons
        self.view_mode = "full"  # Default: full keyspace
        
        full_btn = Gtk.RadioButton.new_with_label_from_widget(None, "Full (0x4-0x7)")
        full_btn.connect("toggled", self.on_view_mode_changed, "full")
        view_mode_box.pack_start(full_btn, False, False, 0)
        
        range_4_btn = Gtk.RadioButton.new_with_label_from_widget(full_btn, "0x4 Only")
        range_4_btn.connect("toggled", self.on_view_mode_changed, "4")
        view_mode_box.pack_start(range_4_btn, False, False, 0)
        
        range_5_btn = Gtk.RadioButton.new_with_label_from_widget(full_btn, "0x5 Only")
        range_5_btn.connect("toggled", self.on_view_mode_changed, "5")
        view_mode_box.pack_start(range_5_btn, False, False, 0)
        
        range_6_btn = Gtk.RadioButton.new_with_label_from_widget(full_btn, "0x6 Only")
        range_6_btn.connect("toggled", self.on_view_mode_changed, "6")
        view_mode_box.pack_start(range_6_btn, False, False, 0)
        
        range_7_btn = Gtk.RadioButton.new_with_label_from_widget(full_btn, "0x7 Only")
        range_7_btn.connect("toggled", self.on_view_mode_changed, "7")
        view_mode_box.pack_start(range_7_btn, False, False, 0)
        
        my_range_btn = Gtk.RadioButton.new_with_label_from_widget(full_btn, "My Range")
        my_range_btn.connect("toggled", self.on_view_mode_changed, "myrange")
        view_mode_box.pack_start(my_range_btn, False, False, 0)
        
        vbox.pack_start(view_mode_box, False, False, 0)
        
        # Stats below bar
        stats_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        stats_box.set_halign(Gtk.Align.CENTER)
        stats_box.set_margin_top(5)
        
        self.coverage_stats_label = Gtk.Label()
        self.coverage_stats_label.set_markup("<span size='small'>Coverage: Calculating...</span>")
        stats_box.pack_start(self.coverage_stats_label, False, False, 0)
        
        # Add refresh button
        refresh_btn = Gtk.Button(label="🔄 Refresh")
        refresh_btn.connect("clicked", self.on_refresh_visualization)
        stats_box.pack_start(refresh_btn, False, False, 0)
        
        vbox.pack_start(stats_box, False, False, 0)
        
        frame.add(vbox)
        return frame
    
    def create_probability_dashboard(self):
        """Create probability of discovery dashboard"""
        frame = Gtk.Frame(label="📊 Probability of Discovery Analysis")
        
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        main_box.set_margin_start(10)
        main_box.set_margin_end(10)
        main_box.set_margin_top(10)
        main_box.set_margin_bottom(10)
        
        # Probability bar (visual)
        prob_bar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        
        # Label
        self.probability_label = Gtk.Label()
        self.probability_label.set_markup("<span size='large' weight='bold'>Current Discovery Probability: Calculating...</span>")
        prob_bar_box.pack_start(self.probability_label, False, False, 0)
        
        # Drawing area for probability bar
        self.probability_drawing = Gtk.DrawingArea()
        self.probability_drawing.set_size_request(-1, 40)
        self.probability_drawing.connect("draw", self.on_draw_probability_bar)
        prob_bar_box.pack_start(self.probability_drawing, False, False, 0)
        
        main_box.pack_start(prob_bar_box, False, False, 0)
        
        # Separator
        main_box.pack_start(Gtk.Separator(), False, False, 0)
        
        # Factors grid
        factors_grid = Gtk.Grid()
        factors_grid.set_column_spacing(15)
        factors_grid.set_row_spacing(8)
        
        row = 0
        
        # Header
        header = Gtk.Label()
        header.set_markup("<span weight='bold' size='large'>Probability Factors:</span>")
        header.set_xalign(0)
        factors_grid.attach(header, 0, row, 3, 1)
        row += 1
        
        # Factor 1: Search Space Coverage
        factors_grid.attach(Gtk.Label(label="1. Search Space Coverage:", xalign=0), 0, row, 1, 1)
        self.prob_factor1_value = Gtk.Label(xalign=0)
        self.prob_factor1_value.set_markup("<span foreground='#CCCCCC'>0.00%</span>")
        factors_grid.attach(self.prob_factor1_value, 1, row, 1, 1)
        self.prob_factor1_impact = Gtk.Label(xalign=0)
        self.prob_factor1_impact.set_markup("<span size='small' foreground='#CCCCCC'>+0.00%</span>")
        factors_grid.attach(self.prob_factor1_impact, 2, row, 1, 1)
        row += 1
        
        # Factor 2: Pattern Filtering
        factors_grid.attach(Gtk.Label(label="2. Pattern Optimization:", xalign=0), 0, row, 1, 1)
        self.prob_factor2_value = Gtk.Label(xalign=0)
        self.prob_factor2_value.set_markup("<span foreground='#CCCCCC'>None active</span>")
        factors_grid.attach(self.prob_factor2_value, 1, row, 1, 1)
        self.prob_factor2_impact = Gtk.Label(xalign=0)
        self.prob_factor2_impact.set_markup("<span size='small' foreground='#CCCCCC'>+0.00%</span>")
        factors_grid.attach(self.prob_factor2_impact, 2, row, 1, 1)
        row += 1
        
        # Factor 3: Pool Coordination
        factors_grid.attach(Gtk.Label(label="3. Pool Coordination:", xalign=0), 0, row, 1, 1)
        self.prob_factor3_value = Gtk.Label(xalign=0)
        self.prob_factor3_value.set_markup("<span foreground='#CCCCCC'>No data</span>")
        factors_grid.attach(self.prob_factor3_value, 1, row, 1, 1)
        self.prob_factor3_impact = Gtk.Label(xalign=0)
        self.prob_factor3_impact.set_markup("<span size='small' foreground='#CCCCCC'>+0.00%</span>")
        factors_grid.attach(self.prob_factor3_impact, 2, row, 1, 1)
        row += 1
        
        # Factor 4: Search Speed
        factors_grid.attach(Gtk.Label(label="4. Search Speed:", xalign=0), 0, row, 1, 1)
        self.prob_factor4_value = Gtk.Label(xalign=0)
        self.prob_factor4_value.set_markup("<span foreground='#CCCCCC'>0 Mk/s</span>")
        factors_grid.attach(self.prob_factor4_value, 1, row, 1, 1)
        self.prob_factor4_impact = Gtk.Label(xalign=0)
        self.prob_factor4_impact.set_markup("<span size='small' foreground='#CCCCCC'>+0.00%</span>")
        factors_grid.attach(self.prob_factor4_impact, 2, row, 1, 1)
        row += 1
        
        # Factor 5: Time Investment
        factors_grid.attach(Gtk.Label(label="5. Time Invested:", xalign=0), 0, row, 1, 1)
        self.prob_factor5_value = Gtk.Label(xalign=0)
        self.prob_factor5_value.set_markup("<span foreground='#CCCCCC'>00:00:00</span>")
        factors_grid.attach(self.prob_factor5_value, 1, row, 1, 1)
        self.prob_factor5_impact = Gtk.Label(xalign=0)
        self.prob_factor5_impact.set_markup("<span size='small' foreground='#CCCCCC'>+0.00%</span>")
        factors_grid.attach(self.prob_factor5_impact, 2, row, 1, 1)
        row += 1
        
        main_box.pack_start(factors_grid, False, False, 0)
        
        # Separator
        main_box.pack_start(Gtk.Separator(), False, False, 0)
        
        # Recommendations
        rec_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        
        rec_header = Gtk.Label()
        rec_header.set_markup("<span weight='bold' foreground='#4CAF50'>💡 Recommendations to Increase Probability:</span>")
        rec_header.set_xalign(0)
        rec_box.pack_start(rec_header, False, False, 0)
        
        self.prob_recommendations = Gtk.Label()
        self.prob_recommendations.set_markup(
            "<span size='small' foreground='#CCCCCC'>Start searching to see recommendations...</span>"
        )
        self.prob_recommendations.set_line_wrap(True)
        self.prob_recommendations.set_xalign(0)
        rec_box.pack_start(self.prob_recommendations, False, False, 0)
        
        main_box.pack_start(rec_box, False, False, 0)
        
        frame.add(main_box)
        return frame
    
    def draw_color_box(self, cr, r, g, b):
        """Draw colored box for legend"""
        cr.set_source_rgb(r, g, b)
        cr.rectangle(0, 0, 20, 20)
        cr.fill()
        return False
    
    def on_draw_probability_bar(self, widget, cr):
        """Draw probability visualization bar"""
        width = widget.get_allocated_width()
        height = widget.get_allocated_height()
        
        # Background (dark grey)
        cr.set_source_rgb(0.2, 0.2, 0.2)
        cr.rectangle(0, 0, width, height)
        cr.fill()
        
        # Calculate current probability
        probability = self.calculate_discovery_probability()
        
        # Draw filled portion based on probability
        if probability > 0:
            # Color gradient based on probability
            if probability < 10:
                # Red (low)
                cr.set_source_rgb(0.9, 0.2, 0.2)
            elif probability < 30:
                # Orange (medium-low)
                cr.set_source_rgb(0.9, 0.6, 0.2)
            elif probability < 60:
                # Yellow (medium)
                cr.set_source_rgb(0.9, 0.9, 0.2)
            else:
                # Green (high)
                cr.set_source_rgb(0.3, 0.8, 0.3)
            
            # Fill bar to probability level
            fill_width = (probability / 100.0) * width
            cr.rectangle(0, 0, fill_width, height)
            cr.fill()
        
        # Draw percentage markers
        cr.set_source_rgb(0.5, 0.5, 0.5)
        cr.set_line_width(1)
        cr.set_font_size(10)
        
        for i in [0, 25, 50, 75, 100]:
            x_pos = (i / 100.0) * width
            
            # Vertical line
            cr.move_to(x_pos, 0)
            cr.line_to(x_pos, height)
            cr.stroke()
            
            # Label
            cr.move_to(x_pos + 2, height - 5)
            cr.show_text(f"{i}%")
        
        return False
    
    def on_view_mode_changed(self, button, mode):
        """Handle view mode change"""
        if button.get_active():
            self.view_mode = mode
            if self.progress_drawing:
                self.progress_drawing.queue_draw()
            self.log(f"📊 View mode: {mode}", "info")
    
    def refresh_block_cache(self):
        """Refresh cached blocks from database - only call when blocks change!"""
        cursor = self.scan_db.conn.cursor()
        cursor.execute('SELECT block_start, block_end FROM pool_scanned ORDER BY block_start')
        self.cached_pool_blocks = cursor.fetchall()
        cursor.execute('SELECT block_start, block_end FROM my_scanned ORDER BY block_start')
        self.cached_my_blocks = cursor.fetchall()
        self.cache_dirty = False
        
        # DEBUG: Print what we loaded
        print(f"\n{'='*60}")
        print(f"CACHE REFRESH")
        print(f"{'='*60}")
        print(f"Loaded {len(self.cached_pool_blocks)} pool blocks from database")
        print(f"Loaded {len(self.cached_my_blocks)} my blocks from database")
        if len(self.cached_pool_blocks) > 0:
            print(f"First pool block: {self.cached_pool_blocks[0][0]} to {self.cached_pool_blocks[0][1]}")
            print(f"Last pool block:  {self.cached_pool_blocks[-1][0]} to {self.cached_pool_blocks[-1][1]}")
        print(f"{'='*60}\n")
    
    def on_draw_progress_bar(self, widget, cr):
        """Draw the visual progress bar"""
        if not self.block_mgr:
            return False
        
        width = widget.get_allocated_width()
        height = widget.get_allocated_height()
        
        # Background (dark grey - unscanned)
        cr.set_source_rgb(0.15, 0.15, 0.15)
        cr.rectangle(0, 0, width, height)
        cr.fill()
        
        # Refresh cache if needed (only when blocks change, not every frame!)
        if self.cache_dirty:
            self.refresh_block_cache()
        
        # Use CACHED blocks (no DB query!)
        pool_blocks = self.cached_pool_blocks
        my_blocks = self.cached_my_blocks
        
        # Determine display range based on view mode
        puzzle_num = self.get_current_puzzle_number()
        if puzzle_num in self.PUZZLE_PRESETS:
            preset = self.PUZZLE_PRESETS[puzzle_num]
            full_range_start = int(preset['range_start'], 16)
            full_range_end = int(preset['range_end'], 16)
        else:
            full_range_start = self.range_start_value
            full_range_end = self.range_end_value
        
        # Adjust range based on view mode
        if self.view_mode == "full":
            # Show entire keyspace
            display_start = full_range_start
            display_end = full_range_end
            frame_label = f"Keyspace Coverage: Full (0x{full_range_start:X} to 0x{full_range_end:X})"
        elif self.view_mode == "myrange":
            # Show only user's configured range
            display_start = self.range_start_value
            display_end = self.range_end_value
            frame_label = f"Keyspace Coverage: My Range (0x{display_start:X} to 0x{display_end:X})"
        elif self.view_mode in ["4", "5", "6", "7"]:
            # Show specific hex prefix range (e.g., all of 0x4... or 0x5...)
            prefix_int = int(self.view_mode, 16)
            # Calculate the range for this prefix in 71-bit space
            # For 71 bits, each prefix covers 1/4 of the space
            range_size = full_range_end - full_range_start + 1
            prefix_size = range_size // 4
            display_start = full_range_start + (prefix_int - 4) * prefix_size
            display_end = display_start + prefix_size - 1
            frame_label = f"Keyspace Coverage: 0x{prefix_int}... Only"
        else:
            display_start = full_range_start
            display_end = full_range_end
            frame_label = "Keyspace Coverage"
        
        total_range = display_end - display_start + 1
        
        # DEBUG: Print what we're about to draw
        print(f"\n{'='*60}")
        print(f"VISUALIZATION DEBUG")
        print(f"{'='*60}")
        print(f"Display range: 0x{display_start:X} to 0x{display_end:X}")
        print(f"Total range size: {total_range:,} keys")
        print(f"Pool blocks in cache: {len(pool_blocks)}")
        print(f"My blocks in cache: {len(my_blocks)}")
        if len(pool_blocks) > 0:
            first_start = int(pool_blocks[0][0], 16)
            first_end = int(pool_blocks[0][1], 16)
            print(f"First pool block: 0x{first_start:X} to 0x{first_end:X}")
        print(f"{'='*60}\n")
        
        # Draw pool scanned blocks (blue) at their ACTUAL positions
        cr.set_source_rgb(0.2, 0.6, 1.0)
        for block_start_hex, block_end_hex in pool_blocks:
            # Convert hex strings back to integers
            block_start = int(block_start_hex, 16)
            block_end = int(block_end_hex, 16)
            
            # Draw blocks that OVERLAP the display range (not just fully contained)
            if block_end >= display_start and block_start <= display_end:
                # Clip to display range
                visible_start = max(block_start, display_start)
                visible_end = min(block_end, display_end)
                
                # Calculate position relative to DISPLAY range
                start_percent = (visible_start - display_start) / total_range
                end_percent = (visible_end - display_start + 1) / total_range
                
                # Convert to pixel positions
                x_start = start_percent * width
                x_end = end_percent * width
                x_width = max(1, x_end - x_start)  # At least 1 pixel visible
                
                cr.rectangle(x_start, 0, x_width, height)
                cr.fill()
        
        # Draw my scanned blocks (green) at their ACTUAL positions
        cr.set_source_rgb(0.3, 0.8, 0.3)
        for block_start_hex, block_end_hex in my_blocks:
            # Convert hex strings back to integers
            block_start = int(block_start_hex, 16)
            block_end = int(block_end_hex, 16)
            
            # Draw blocks that OVERLAP the display range
            if block_end >= display_start and block_start <= display_end:
                # Clip to display range
                visible_start = max(block_start, display_start)
                visible_end = min(block_end, display_end)
                
                # Calculate position relative to DISPLAY range
                start_percent = (visible_start - display_start) / total_range
                end_percent = (visible_end - display_start + 1) / total_range
                
                # Convert to pixel positions
                x_start = start_percent * width
                x_end = end_percent * width
                x_width = max(1, x_end - x_start)
                
                cr.rectangle(x_start, 0, x_width, height)
                cr.fill()
        
        # Draw currently scanning block (yellow/orange) at its ACTUAL position
        if self.current_block and self.is_running:
            block_start, block_end = self.current_block
            
            # Only draw if block is in display range
            if block_start >= display_start and block_end <= display_end:
                # Calculate block position
                start_percent = (block_start - display_start) / total_range
                end_percent = (block_end - display_start + 1) / total_range
                
                # Convert to pixel positions
                x_start = start_percent * width
                x_end = end_percent * width
                x_width = max(2, x_end - x_start)
                
                # Draw full block boundary (yellow outline)
                cr.set_source_rgb(1.0, 0.8, 0.2)
                cr.rectangle(x_start, 0, x_width, height)
                cr.fill()
                
                # Calculate progress within this block
                keys_in_block = block_end - block_start + 1
                block_progress = min(1.0, self.keys_checked / keys_in_block) if keys_in_block > 0 else 0
                
                # Draw progress bar within the block (brighter yellow/orange)
                if block_progress > 0:
                    cr.set_source_rgb(1.0, 0.6, 0.0)  # Brighter orange
                    progress_width = x_width * block_progress
                    cr.rectangle(x_start, 0, progress_width, height)
                    cr.fill()
                
                # Draw percentage text on the block
                cr.set_source_rgb(0, 0, 0)  # Black text
                cr.set_font_size(12)
                percent_text = f"{block_progress * 100:.1f}%"
                text_extents = cr.text_extents(percent_text)
                text_x = x_start + (x_width - text_extents.width) / 2
                text_y = height / 2 + text_extents.height / 2
                cr.move_to(text_x, text_y)
                cr.show_text(percent_text)
        
        # Draw user's search range indicator (semi-transparent overlay)
        if full_range_start != self.range_start_value or full_range_end != self.range_end_value:
            # User is searching a subset - show it
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.1)  # White semi-transparent
            
            user_start_percent = (self.range_start_value - full_range_start) / total_range
            user_end_percent = (self.range_end_value - full_range_start + 1) / total_range
            
            x_start = user_start_percent * width
            x_end = user_end_percent * width
            
            cr.rectangle(x_start, 0, x_end - x_start, height)
            cr.fill()
            
            # Draw borders for user range
            cr.set_source_rgb(1.0, 1.0, 1.0)
            cr.set_line_width(2)
            cr.move_to(x_start, 0)
            cr.line_to(x_start, height)
            cr.stroke()
            cr.move_to(x_end, 0)
            cr.line_to(x_end, height)
            cr.stroke()
        
        # Draw percentage markers (every 10%)
        cr.set_source_rgb(0.5, 0.5, 0.5)
        cr.set_line_width(1)
        cr.set_font_size(10)
        
        for i in range(0, 11):  # 0%, 10%, 20%, ... 100%
            x_pos = (i / 10.0) * width
            
            # Vertical tick mark
            cr.move_to(x_pos, height - 5)
            cr.line_to(x_pos, height)
            cr.stroke()
            
            # Percentage label
            if i % 2 == 0:  # Only label every 20% to avoid crowding
                label = f"{i*10}%"
                extents = cr.text_extents(label)
                label_x = x_pos - extents.width / 2
                label_y = height - 8
                
                cr.move_to(label_x, label_y)
                cr.show_text(label)
        
        # Border
        cr.set_source_rgb(0.5, 0.5, 0.5)
        cr.set_line_width(1)
        cr.rectangle(0, 0, width, height)
        cr.stroke()
        
        # Update coverage stats
        self.update_coverage_stats()
        
        return False
    
    def on_refresh_visualization(self, button):
        """Manually refresh the keyspace visualization"""
        self.cache_dirty = True  # Force cache refresh
        if self.progress_drawing:
            self.progress_drawing.queue_draw()
        self.update_coverage_stats()
        self.log("🔄 Visualization refreshed", "info")
    
    def clear_pool_data(self):
        """Clear all pool scanned data - use after fixing range issues"""
        if self.is_running:
            self.log("⚠️ Cannot clear pool data while running!", "warning")
            return
        
        cursor = self.scan_db.conn.cursor()
        cursor.execute('DELETE FROM pool_scanned')
        self.scan_db.conn.commit()
        self.cache_dirty = True
        self.log("🗑️ Cleared all pool data - will re-scrape on next start", "success")
        
        # Force immediate re-scrape
        self.scrape_pool()
    
    def update_coverage_stats(self):
        """Update coverage statistics text based on current view mode"""
        if not self.block_mgr:
            return
        
        # Determine display range based on view mode
        puzzle_num = self.get_current_puzzle_number()
        if puzzle_num in self.PUZZLE_PRESETS:
            preset = self.PUZZLE_PRESETS[puzzle_num]
            full_range_start = int(preset['range_start'], 16)
            full_range_end = int(preset['range_end'], 16)
        else:
            full_range_start = self.range_start_value
            full_range_end = self.range_end_value
        
        # Adjust range based on view mode
        if self.view_mode == "full":
            display_start = full_range_start
            display_end = full_range_end
        elif self.view_mode == "myrange":
            display_start = self.range_start_value
            display_end = self.range_end_value
        elif self.view_mode in ["4", "5", "6", "7"]:
            prefix_int = int(self.view_mode, 16)
            range_size = full_range_end - full_range_start + 1
            prefix_size = range_size // 4
            display_start = full_range_start + (prefix_int - 4) * prefix_size
            display_end = display_start + prefix_size - 1
        else:
            display_start = full_range_start
            display_end = full_range_end
        
        full_keyspace = display_end - display_start + 1
        
        # Count blocks within the DISPLAY range
        cursor = self.scan_db.conn.cursor()
        cursor.execute('SELECT block_start, block_end FROM pool_scanned')
        all_pool_blocks = cursor.fetchall()
        
        # Count OVERLAPPING pool blocks and calculate their total coverage
        pool_coverage_keys = 0
        for block_start_hex, block_end_hex in all_pool_blocks:
            block_start = int(block_start_hex, 16)
            block_end = int(block_end_hex, 16)
            # Check if block overlaps the display range
            if block_end >= display_start and block_start <= display_end:
                # Calculate the overlapping portion
                overlap_start = max(block_start, display_start)
                overlap_end = min(block_end, display_end)
                overlap_keys = overlap_end - overlap_start + 1
                pool_coverage_keys += overlap_keys
        
        cursor.execute('SELECT block_start, block_end FROM my_scanned')
        all_my_blocks = cursor.fetchall()
        
        # Count OVERLAPPING my blocks and calculate their total coverage
        my_coverage_keys = 0
        for block_start_hex, block_end_hex in all_my_blocks:
            block_start = int(block_start_hex, 16)
            block_end = int(block_end_hex, 16)
            # Check if block overlaps the display range
            if block_end >= display_start and block_start <= display_end:
                # Calculate the overlapping portion
                overlap_start = max(block_start, display_start)
                overlap_end = min(block_end, display_end)
                overlap_keys = overlap_end - overlap_start + 1
                my_coverage_keys += overlap_keys
        
        # Calculate percentages based on ACTUAL key coverage
        pool_percent = (pool_coverage_keys / full_keyspace) * 100 if full_keyspace > 0 else 0
        my_percent = (my_coverage_keys / full_keyspace) * 100 if full_keyspace > 0 else 0
        total_percent = pool_percent + my_percent
        unscanned_percent = 100 - total_percent
        
        coverage_text = (
            f"<span size='small'>"
            f"Pool: <span foreground='#3399FF'>{pool_percent:.5f}%</span> | "
            f"Mine: <span foreground='#4CAF50'>{my_percent:.5f}%</span> | "
            f"Total: <span foreground='#FFCC00'>{total_percent:.5f}%</span> | "
            f"Remaining: <span foreground='#CCCCCC'>{unscanned_percent:.5f}%</span>"
            f"</span>"
        )
        
        self.coverage_stats_label.set_markup(coverage_text)
    
    def create_config_page(self):
        """Create configuration page"""
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        
        grid = Gtk.Grid()
        grid.set_column_spacing(10)
        grid.set_row_spacing(10)
        grid.set_margin_start(10)
        grid.set_margin_end(10)
        grid.set_margin_top(10)
        grid.set_margin_bottom(10)
        scrolled.add(grid)
        
        row = 0
        
        # Puzzle Selector (BIG AND PROMINENT)
        puzzle_frame = Gtk.Frame()
        # Create a label with markup for the frame
        frame_label = Gtk.Label()
        frame_label.set_markup("<span foreground='#FF9800' weight='bold' size='large'> 🎯 SELECT PUZZLE </span>")
        puzzle_frame.set_label_widget(frame_label)
        
        puzzle_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        puzzle_box.set_margin_start(10)
        puzzle_box.set_margin_end(10)
        puzzle_box.set_margin_top(10)
        puzzle_box.set_margin_bottom(10)
        
        # Puzzle dropdown
        puzzle_select_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl = Gtk.Label(xalign=0)
        lbl.set_markup("<span foreground='#000000' weight='bold'>Puzzle Number:</span>")
        puzzle_select_box.pack_start(lbl, False, False, 0)
        
        self.puzzle_combo = Gtk.ComboBoxText()
        for puzzle_num in sorted(self.PUZZLE_PRESETS.keys()):
            preset = self.PUZZLE_PRESETS[puzzle_num]
            self.puzzle_combo.append_text(f"#{puzzle_num} - {preset['bits']} bits - {preset['reward']}")
        self.puzzle_combo.set_active(0)  # Default to #71 (first unsolved puzzle)
        self.puzzle_combo.connect("changed", self.on_puzzle_changed)
        puzzle_select_box.pack_start(self.puzzle_combo, False, False, 0)
        
        # Load preset button
        load_preset_btn = Gtk.Button(label="📋 Load Preset")
        load_preset_btn.connect("clicked", self.on_load_preset)
        puzzle_select_box.pack_start(load_preset_btn, False, False, 0)
        
        puzzle_box.pack_start(puzzle_select_box, False, False, 0)
        
        # Info about current puzzle
        self.puzzle_info_label = Gtk.Label()
        self.puzzle_info_label.set_markup("<span size='small'>Current: Puzzle #71 - 71 bits - Reward: 7.1 BTC</span>")
        self.puzzle_info_label.set_line_wrap(True)
        puzzle_box.pack_start(self.puzzle_info_label, False, False, 0)
        
        # Database info
        self.db_info_label = Gtk.Label()
        self.db_info_label.set_markup("<span size='small' foreground='#CCCCCC'>Database: scan_data_puzzle_71.db</span>")
        puzzle_box.pack_start(self.db_info_label, False, False, 0)
        
        puzzle_frame.add(puzzle_box)
        grid.attach(puzzle_frame, 0, row, 3, 1)
        row += 1
        
        # Separator
        grid.attach(Gtk.Separator(), 0, row, 3, 1)
        row += 1
        
        # KeyHunt Path
        lbl = Gtk.Label(xalign=0)
        lbl.set_markup("<span foreground='#000000' weight='bold'>KeyHunt Path:</span>")
        grid.attach(lbl, 0, row, 1, 1)
        self.keyhunt_path = Gtk.Entry()
        self.keyhunt_path.set_text("./KeyHunt-Cuda")
        grid.attach(self.keyhunt_path, 1, row, 1, 1)
        browse_btn = Gtk.Button(label="Browse...")
        browse_btn.connect("clicked", self.on_keyhunt_browse)
        grid.attach(browse_btn, 2, row, 1, 1)
        row += 1
        
        # Target Address
        lbl = Gtk.Label(xalign=0)
        lbl.set_markup("<span foreground='#000000' weight='bold'>Target Address:</span>")
        grid.attach(lbl, 0, row, 1, 1)
        self.target_entry = Gtk.Entry()
        self.target_entry.set_text("1PWo3JeB9jrGwfHDNpdGK54CRas7fsVzXU")
        grid.attach(self.target_entry, 1, row, 2, 1)
        row += 1
        
        # Range Start
        lbl = Gtk.Label(xalign=0)
        lbl.set_markup("<span foreground='#000000' weight='bold'>Range Start (Hex):</span>")
        grid.attach(lbl, 0, row, 1, 1)
        self.range_start = Gtk.Entry()
        self.range_start.set_text("7000000000000000")
        grid.attach(self.range_start, 1, row, 2, 1)
        row += 1
        
        # Range End
        lbl = Gtk.Label(xalign=0)
        lbl.set_markup("<span foreground='#000000' weight='bold'>Range End (Hex):</span>")
        grid.attach(lbl, 0, row, 1, 1)
        self.range_end = Gtk.Entry()
        self.range_end.set_text("7FFFFFFFFFFFFFFF")
        grid.attach(self.range_end, 1, row, 2, 1)
        row += 1
        
        # Block Size
        lbl = Gtk.Label(xalign=0)
        lbl.set_markup("<span foreground='#000000' weight='bold'>Block Size (hex):</span>")
        grid.attach(lbl, 0, row, 1, 1)
        self.block_size = Gtk.Entry()
        self.block_size.set_text("1FFFFFFFFFF")  # 2.2 trillion keys (~2.7 hours on GTX 1070)
        help_label = Gtk.Label(label="(~2.2 trillion keys, ~162 minutes on GTX 1070)")
        help_label.set_sensitive(False)
        grid.attach(self.block_size, 1, row, 1, 1)
        grid.attach(help_label, 2, row, 1, 1)
        row += 1
        
        # Pattern Exclusion Filters
        grid.attach(Gtk.Separator(), 0, row, 3, 1)
        row += 1
        
        pattern_frame = Gtk.Frame(label=" 🎯 PATTERN EXCLUSION FILTERS ")
        pattern_grid = Gtk.Grid()
        pattern_grid.set_column_spacing(10)
        pattern_grid.set_row_spacing(5)
        pattern_grid.set_margin_start(10)
        pattern_grid.set_margin_end(10)
        pattern_grid.set_margin_top(10)
        pattern_grid.set_margin_bottom(10)
        
        pattern_row = 0
        
        # Info label
        info_label = Gtk.Label()
        info_label.set_markup(
            "<span size='small' foreground='#CCCCCC'>"
            "Exclude patterns statistically unlikely in random keys\n"
            "Reduces search space by 40-70% while maintaining coverage"
            "</span>"
        )
        info_label.set_line_wrap(True)
        info_label.set_xalign(0)
        pattern_grid.attach(info_label, 0, pattern_row, 3, 1)
        pattern_row += 1
        
        # Exclude Iterated 3
        self.exclude_iter3 = Gtk.CheckButton()
        lbl = Gtk.Label()
        lbl.set_markup("<span foreground='#000000' weight='bold'>Exclude 3+ repeated characters</span>")
        self.exclude_iter3.add(lbl)
        self.exclude_iter3.set_active(False)
        pattern_grid.attach(self.exclude_iter3, 0, pattern_row, 2, 1)
        
        iter3_info = Gtk.Label()
        iter3_info.set_markup("<span size='small' foreground='#DDDDDD'>~60% reduction</span>")
        iter3_info.set_xalign(0)
        pattern_grid.attach(iter3_info, 2, pattern_row, 1, 1)
        pattern_row += 1
        
        iter3_example = Gtk.Label()
        iter3_example.set_markup(
            "<span size='small' font='monospace' foreground='#DDDDDD'>"
            "Skips: 0x7000000..., 0x7111111..., 0x7FFF..."
            "</span>"
        )
        iter3_example.set_xalign(0)
        iter3_example.set_margin_start(25)
        pattern_grid.attach(iter3_example, 0, pattern_row, 3, 1)
        pattern_row += 1
        
        # Exclude Iterated 4
        self.exclude_iter4 = Gtk.CheckButton()
        lbl = Gtk.Label()
        lbl.set_markup("<span foreground='#000000' weight='bold'>Exclude 4+ repeated characters</span>")
        self.exclude_iter4.add(lbl)
        self.exclude_iter4.set_active(False)
        pattern_grid.attach(self.exclude_iter4, 0, pattern_row, 2, 1)
        
        iter4_info = Gtk.Label()
        iter4_info.set_markup("<span size='small' foreground='#DDDDDD'>~40% reduction</span>")
        iter4_info.set_xalign(0)
        pattern_grid.attach(iter4_info, 2, pattern_row, 1, 1)
        pattern_row += 1
        
        iter4_example = Gtk.Label()
        iter4_example.set_markup(
            "<span size='small' font='monospace' foreground='#DDDDDD'>"
            "Skips: 0x70000000..., 0x7AAAA..., 0x7FFFF..."
            "</span>"
        )
        iter4_example.set_xalign(0)
        iter4_example.set_margin_start(25)
        pattern_grid.attach(iter4_example, 0, pattern_row, 3, 1)
        pattern_row += 1
        
        # Exclude Alpha/Numeric only
        self.exclude_alphanum = Gtk.CheckButton()
        lbl = Gtk.Label()
        lbl.set_markup("<span foreground='#000000' weight='bold'>Exclude all-letters or all-numbers</span>")
        self.exclude_alphanum.add(lbl)
        self.exclude_alphanum.set_active(False)
        pattern_grid.attach(self.exclude_alphanum, 0, pattern_row, 2, 1)
        
        alphanum_info = Gtk.Label()
        alphanum_info.set_markup("<span size='small' foreground='#DDDDDD'>~30% reduction</span>")
        alphanum_info.set_xalign(0)
        pattern_grid.attach(alphanum_info, 2, pattern_row, 1, 1)
        pattern_row += 1
        
        alphanum_example = Gtk.Label()
        alphanum_example.set_markup(
            "<span size='small' font='monospace' foreground='#DDDDDD'>"
            "Skips: 0x777777..., 0xABCDEF..., 0x123456..."
            "</span>"
        )
        alphanum_example.set_xalign(0)
        alphanum_example.set_margin_start(25)
        pattern_grid.attach(alphanum_example, 0, pattern_row, 3, 1)
        pattern_row += 1
        
        # Combined reduction estimate
        self.pattern_reduction_label = Gtk.Label()
        self.pattern_reduction_label.set_markup(
            "<span foreground='#00FFFF' weight='bold'>Estimated search space reduction: 0%</span>"
        )
        self.pattern_reduction_label.set_xalign(0)
        pattern_grid.attach(self.pattern_reduction_label, 0, pattern_row, 3, 1)
        
        # Connect checkboxes to update reduction estimate
        self.exclude_iter3.connect("toggled", self.update_pattern_reduction)
        self.exclude_iter4.connect("toggled", self.update_pattern_reduction)
        self.exclude_alphanum.connect("toggled", self.update_pattern_reduction)
        
        pattern_frame.add(pattern_grid)
        grid.attach(pattern_frame, 0, row, 3, 1)
        row += 1
        
        # GPU Settings
        grid.attach(Gtk.Separator(), 0, row, 3, 1)
        row += 1
        
        grid.attach(Gtk.Label(label="GPU ID:", xalign=0), 0, row, 1, 1)
        self.gpu_id = Gtk.Entry()
        self.gpu_id.set_text("0")
        grid.attach(self.gpu_id, 1, row, 2, 1)
        row += 1
        
        # CONTROL BUTTONS (duplicated here for easy access)
        grid.attach(Gtk.Separator(), 0, row, 3, 1)
        row += 1
        
        controls_frame = Gtk.Frame(label=" 🎮 CONTROLS ")
        controls_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        controls_box.set_halign(Gtk.Align.CENTER)
        controls_box.set_margin_start(10)
        controls_box.set_margin_end(10)
        controls_box.set_margin_top(10)
        controls_box.set_margin_bottom(10)
        
        self.start_btn_config = Gtk.Button(label="▶ Start")
        self.start_btn_config.connect("clicked", self.on_start)
        self.start_btn_config.set_size_request(120, 40)
        controls_box.pack_start(self.start_btn_config, False, False, 0)
        
        self.pause_btn_config = Gtk.Button(label="⏸ Pause")
        self.pause_btn_config.connect("clicked", self.on_pause)
        self.pause_btn_config.set_sensitive(False)
        self.pause_btn_config.set_size_request(120, 40)
        controls_box.pack_start(self.pause_btn_config, False, False, 0)
        
        self.stop_btn_config = Gtk.Button(label="⏹ Stop")
        self.stop_btn_config.connect("clicked", self.on_stop)
        self.stop_btn_config.set_sensitive(False)
        self.stop_btn_config.set_size_request(120, 40)
        controls_box.pack_start(self.stop_btn_config, False, False, 0)
        
        scrape_btn_config = Gtk.Button(label="🔄 Scrape Pool Now")
        scrape_btn_config.connect("clicked", self.on_manual_scrape)
        scrape_btn_config.set_size_request(150, 40)
        controls_box.pack_start(scrape_btn_config, False, False, 0)
        
        controls_frame.add(controls_box)
        grid.attach(controls_frame, 0, row, 3, 1)
        row += 1
        
        return scrolled
    
    def create_console_page(self):
        """Create console output page"""
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        
        self.console_view = Gtk.TextView()
        self.console_view.set_editable(False)
        self.console_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.console_view.set_monospace(True)
        
        # Use CSS for styling instead of deprecated methods
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b"""
            textview {
                background-color: #1a1a1a;
                color: #dddddd;
            }
        """)
        context = self.console_view.get_style_context()
        context.add_provider(css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        
        self.console_buffer = self.console_view.get_buffer()
        
        # Tags for colored output (high contrast colors for dark background)
        self.console_buffer.create_tag("info", foreground="#DDDDDD")
        self.console_buffer.create_tag("success", foreground="#00FFFF", weight=Pango.Weight.BOLD)  # Bright cyan instead of green
        self.console_buffer.create_tag("warning", foreground="#FFAA00")
        self.console_buffer.create_tag("error", foreground="#FF6666", weight=Pango.Weight.BOLD)
        self.console_buffer.create_tag("match", foreground="#00FFFF", weight=Pango.Weight.BOLD)  # Bright cyan for matches
        
        scrolled.add(self.console_view)
        return scrolled
    
    def create_blocks_page(self):
        """Create block manager view with edit/delete capabilities"""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_start(10)
        box.set_margin_end(10)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        
        # Refresh button
        refresh_btn = Gtk.Button(label="🔄 Refresh Block List")
        refresh_btn.connect("clicked", self.on_refresh_blocks)
        box.pack_start(refresh_btn, False, False, 0)
        
        # Block info
        info_frame = Gtk.Frame(label="Block Information")
        info_grid = Gtk.Grid()
        info_grid.set_column_spacing(10)
        info_grid.set_row_spacing(5)
        info_grid.set_margin_start(10)
        info_grid.set_margin_end(10)
        info_grid.set_margin_top(10)
        info_grid.set_margin_bottom(10)
        info_frame.add(info_grid)
        
        info_grid.attach(Gtk.Label(label="Total Blocks:", xalign=0), 0, 0, 1, 1)
        self.total_blocks_label = Gtk.Label(label="0", xalign=0)
        info_grid.attach(self.total_blocks_label, 1, 0, 1, 1)
        
        info_grid.attach(Gtk.Label(label="Blocks Remaining:", xalign=0), 0, 1, 1, 1)
        self.remaining_blocks_label = Gtk.Label(label="0", xalign=0)
        info_grid.attach(self.remaining_blocks_label, 1, 1, 1, 1)
        
        info_grid.attach(Gtk.Label(label="Current Block Progress:", xalign=0), 0, 2, 1, 1)
        self.block_progress_label = Gtk.Label(label="0%", xalign=0)
        info_grid.attach(self.block_progress_label, 1, 2, 1, 1)
        
        box.pack_start(info_frame, False, False, 0)
        
        # Block list with TreeView (selectable rows)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        
        # Create ListStore: Index, Start, End, Size, Status
        self.block_store = Gtk.ListStore(int, str, str, str, str, str, str)  # index, start, end, size, status, start_int, end_int
        
        self.block_tree_view = Gtk.TreeView(model=self.block_store)
        self.block_tree_view.set_name("block_tree_view")
        
        # Add columns
        columns = [
            ("Index", 0),
            ("Start", 1),
            ("End", 2),
            ("Size (keys)", 3),
            ("Status", 4)
        ]
        
        for title, col_id in columns:
            renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(title, renderer, text=col_id)
            column.set_resizable(True)
            column.set_sort_column_id(col_id)
            self.block_tree_view.append_column(column)
        
        # Add right-click context menu
        self.block_tree_view.connect("button-press-event", self.on_block_right_click)
        
        # Style
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b"""
            #block_tree_view {
                background-color: #1a1a1a;
                color: #e5e5e5;
            }
        """)
        context = self.block_tree_view.get_style_context()
        context.add_provider(css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        
        scrolled.add(self.block_tree_view)
        
        box.pack_start(scrolled, True, True, 0)
        
        # Initial population
        GLib.timeout_add(500, self.populate_blocks_view)
        
        return box
    
    def create_exclusions_page(self):
        """Create exclusions view"""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_start(10)
        box.set_margin_end(10)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        
        # Refresh button
        refresh_btn = Gtk.Button(label="🔄 Refresh Exclusion List")
        refresh_btn.connect("clicked", self.on_refresh_exclusions)
        box.pack_start(refresh_btn, False, False, 0)
        
        # Info label
        info_label = Gtk.Label()
        info_label.set_markup(
            "<b>Excluded Ranges:</b>\n"
            "Blocks that have been scanned by the pool or by you"
        )
        info_label.set_xalign(0)
        box.pack_start(info_label, False, False, 0)
        
        # Exclusions list (scrollable)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        
        self.exclusions_view = Gtk.TextView()
        self.exclusions_view.set_editable(False)
        self.exclusions_view.set_monospace(True)
        self.exclusions_view.set_name("exclusions_view")
        
        # Use CSS for styling
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b"""
            #exclusions_view {
                background-color: #1a1a1a;
                color: #e5e5e5;
            }
        """)
        context = self.exclusions_view.get_style_context()
        context.add_provider(css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        
        scrolled.add(self.exclusions_view)
        box.pack_start(scrolled, True, True, 0)
        
        # Initial population
        GLib.timeout_add(500, self.populate_exclusions_view)
        
        return box
    
    def create_manual_input_page(self):
        """Create manual range input page"""
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        main_box.set_margin_start(10)
        main_box.set_margin_end(10)
        main_box.set_margin_top(10)
        main_box.set_margin_bottom(10)
        
        # Instructions
        info_frame = Gtk.Frame(label="📝 Manual Range Input")
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        info_box.set_margin_start(10)
        info_box.set_margin_end(10)
        info_box.set_margin_top(10)
        info_box.set_margin_bottom(10)
        
        info_label = Gtk.Label()
        info_label.set_markup(
            "<b>Add ranges manually from other sources:</b>\n"
            "• Copy/paste ranges from other pool websites\n"
            "• Import data from local files\n"
            "• Manually exclude specific keyspace regions\n\n"
            "<b>Supported formats:</b>\n"
            "• START:END (hex)\n"
            "• START-END (hex)\n"
            "• START END (hex)\n"
            "• One range per line"
        )
        info_label.set_line_wrap(True)
        info_label.set_xalign(0)
        info_box.pack_start(info_label, False, False, 0)
        info_frame.add(info_box)
        main_box.pack_start(info_frame, False, False, 0)
        
        # Input area
        input_frame = Gtk.Frame(label="Enter Ranges (one per line)")
        input_scroll = Gtk.ScrolledWindow()
        input_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        input_scroll.set_size_request(-1, 200)
        
        self.manual_input_view = Gtk.TextView()
        self.manual_input_view.set_monospace(True)
        self.manual_input_view.set_wrap_mode(Gtk.WrapMode.WORD)
        input_scroll.add(self.manual_input_view)
        input_frame.add(input_scroll)
        main_box.pack_start(input_frame, True, True, 0)
        
        # Example text
        example_frame = Gtk.Frame(label="Examples")
        example_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        example_box.set_margin_start(10)
        example_box.set_margin_end(10)
        example_box.set_margin_top(5)
        example_box.set_margin_bottom(5)
        
        example_label = Gtk.Label()
        example_label.set_markup(
            "<span font='monospace' size='small'>"
            "7000000000000000:700000000FFFFFFF\n"
            "7100000000000000-710000000FFFFFFF\n"
            "7200000000000000 720000000FFFFFFF"
            "</span>"
        )
        example_label.set_xalign(0)
        example_box.pack_start(example_label, False, False, 0)
        example_frame.add(example_box)
        main_box.pack_start(example_frame, False, False, 0)
        
        # Buttons
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_box.set_halign(Gtk.Align.CENTER)
        
        # Add as pool scanned
        pool_btn = Gtk.Button(label="➕ Add as Pool Scanned")
        pool_btn.connect("clicked", self.on_add_manual_pool_ranges)
        pool_btn.set_size_request(200, 40)
        button_box.pack_start(pool_btn, False, False, 0)
        
        # Add as my scanned
        my_btn = Gtk.Button(label="➕ Add as My Scanned")
        my_btn.connect("clicked", self.on_add_manual_my_ranges)
        my_btn.set_size_request(200, 40)
        button_box.pack_start(my_btn, False, False, 0)
        
        # Import from file
        import_btn = Gtk.Button(label="📁 Import from File")
        import_btn.connect("clicked", self.on_import_ranges_file)
        import_btn.set_size_request(200, 40)
        button_box.pack_start(import_btn, False, False, 0)
        
        # Clear
        clear_btn = Gtk.Button(label="🗑 Clear Input")
        clear_btn.connect("clicked", self.on_clear_manual_input)
        clear_btn.set_size_request(150, 40)
        button_box.pack_start(clear_btn, False, False, 0)
        
        main_box.pack_start(button_box, False, False, 0)
        
        # Status
        self.manual_status_label = Gtk.Label()
        self.manual_status_label.set_markup("<span foreground='#CCCCCC'>Ready to import ranges</span>")
        main_box.pack_start(self.manual_status_label, False, False, 0)
        
        return main_box
    
    def create_controls(self):
        """Create control buttons"""
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box.set_halign(Gtk.Align.CENTER)
        
        self.start_btn = Gtk.Button(label="▶ Start")
        self.start_btn.connect("clicked", self.on_start)
        self.start_btn.set_size_request(120, 40)
        box.pack_start(self.start_btn, False, False, 0)
        
        self.pause_btn = Gtk.Button(label="⏸ Pause")
        self.pause_btn.connect("clicked", self.on_pause)
        self.pause_btn.set_sensitive(False)
        self.pause_btn.set_size_request(120, 40)
        box.pack_start(self.pause_btn, False, False, 0)
        
        self.stop_btn = Gtk.Button(label="⏹ Stop")
        self.stop_btn.connect("clicked", self.on_stop)
        self.stop_btn.set_sensitive(False)
        self.stop_btn.set_size_request(120, 40)
        box.pack_start(self.stop_btn, False, False, 0)
        
        scrape_btn = Gtk.Button(label="🔄 Scrape Pool Now")
        scrape_btn.connect("clicked", self.on_manual_scrape)
        scrape_btn.set_size_request(150, 40)
        box.pack_start(scrape_btn, False, False, 0)
        
        return box
    
    def apply_css(self):
        """Apply CSS styling"""
        css_provider = Gtk.CssProvider()
        css = b"""
        window {
            background-color: #1e1e1e;
            color: #ffffff;
        }
        """
        css_provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(
            self.get_screen(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
    
    def log(self, message, tag="info"):
        """Log message to console - thread-safe wrapper"""
        # If not on main thread, schedule on main thread
        if threading.current_thread() != threading.main_thread():
            GLib.idle_add(self._log_impl, message, tag)
        else:
            self._log_impl(message, tag)
    
    def _log_impl(self, message, tag="info"):
        """Internal log implementation - must run on main thread"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Get end iterator and insert timestamp
        end_iter = self.console_buffer.get_end_iter()
        self.console_buffer.insert(end_iter, f"[{timestamp}] ")
        
        # Get fresh end iterator for message (previous one is invalid after insert)
        end_iter = self.console_buffer.get_end_iter()
        self.console_buffer.insert_with_tags_by_name(end_iter, f"{message}\n", tag)
        
        # Auto-scroll to end
        end_mark = self.console_buffer.create_mark(None, self.console_buffer.get_end_iter(), False)
        self.console_view.scroll_to_mark(end_mark, 0.0, True, 0.0, 1.0)
        self.console_buffer.delete_mark(end_mark)
        
        return False  # Don't repeat if called via GLib.idle_add
    
    def start_pool_scraper(self):
        """Start background pool scraper thread"""
        def scraper_loop():
            while True:
                if not self.is_running or datetime.now().timestamp() - (self.last_pool_scrape or 0) > self.scrape_interval:
                    GLib.idle_add(self.scrape_pool)
                threading.Event().wait(60)  # Check every minute
        
        thread = threading.Thread(target=scraper_loop, daemon=True)
        thread.start()
    
    def scrape_pool(self):
        """Scrape pool for scanned ranges"""
        self.log("=" * 60, "info")
        self.log("🌐 STARTING POOL SCRAPE FROM LIVE WEBSITE", "info")
        self.log("=" * 60, "info")
        self.log(f"🔗 URL: https://btcpuzzle.info/puzzle/{self.get_current_puzzle_number()}", "info")
        self.log("📡 Fetching data... (this is NOT hardcoded!)", "info")
        
        try:
            # The print statements from pool_scraper will show in terminal
            scanned_blocks = self.pool_scraper.scrape_scanned_ranges()
            
            if scanned_blocks:
                self.log(f"📦 Received {len(scanned_blocks)} blocks from website", "success")
                
                # Check for collision with current block BEFORE adding to database
                collision_detected = False
                if self.current_block and self.is_running:
                    current_start, current_end = self.current_block
                    for block_start, block_end in scanned_blocks:
                        # Check if pool just scanned our current block
                        if block_start == current_start and block_end == current_end:
                            collision_detected = True
                            self.log("⚠️ COLLISION DETECTED! Pool completed our current block!", "warning")
                            break
                
                # Add blocks to database and get counts
                added_count, duplicate_count = self.scan_db.add_pool_blocks(scanned_blocks)
                self.cache_dirty = True  # Refresh cache on next redraw
                
                # Get total pool blocks in database
                total_pool_blocks = len(self.scan_db.conn.execute('SELECT * FROM pool_scanned').fetchall())
                
                # Show stats about what was added
                self.log(f"📊 Pool Scrape Results:", "info")
                self.log(f"   • Found from website: {len(scanned_blocks)} blocks", "info")
                self.log(f"   • New blocks added: {added_count}", "success" if added_count > 0 else "info")
                self.log(f"   • Already in database: {duplicate_count}", "info")
                self.log(f"   • Total pool blocks now: {total_pool_blocks}", "info")
                
                # DIAGNOSTIC: Show range of pool blocks
                if scanned_blocks:
                    starts = []
                    ends = []
                    for b in scanned_blocks:
                        # Handle both string and int formats
                        start = int(b[0], 16) if isinstance(b[0], str) else b[0]
                        end = int(b[1], 16) if isinstance(b[1], str) else b[1]
                        starts.append(start)
                        ends.append(end)
                    min_start = hex(min(starts))
                    max_end = hex(max(ends))
                    
                    self.log(f"📊 Range Summary:", "info")
                    self.log(f"   • Earliest block: {min_start}", "info")
                    self.log(f"   • Latest block: {max_end}", "info")
                
                self.log(f"✅ Pool scrape complete!", "success")
                self.log("💡 Check terminal/console for detailed scrape log!", "info")
                self.last_pool_scrape = datetime.now().timestamp()
                self.update_smart_status()
                
                # Update probability dashboard
                GLib.idle_add(self.update_probability_dashboard)
                
                # Handle collision - switch to new block
                if collision_detected:
                    GLib.idle_add(self.handle_block_collision)
                
                # Redraw visual progress bar
                if self.progress_drawing:
                    GLib.idle_add(self.progress_drawing.queue_draw)
            else:
                self.log("⚠ Pool scrape: No new ranges found", "warning")
                
        except Exception as e:
            self.log(f"❌ Pool scrape failed: {e}", "error")
    
    def handle_block_collision(self):
        """Handle collision - pool completed our current block"""
        self.log("🔄 Switching to fresh block due to collision...", "warning")
        
        # Stop current search
        if self.process:
            self.process.terminate()
            self.process = None
        
        # Mark current block as scanned by pool (already in DB)
        # Don't add to my_scanned since we didn't complete it
        
        # Find next unscanned block
        self.current_block_index += 1
        self.keys_checked = 0
        self.find_next_block()
        
        if self.current_block:
            self.log(f"✅ Switched to fresh block #{self.current_block_index}", "success")
            # Continue searching
            thread = threading.Thread(target=self.run_block_search, daemon=True)
            thread.start()
        else:
            self.log("✅ No more fresh blocks available!", "success")
            self.on_stop(None)
    
    def on_manual_scrape(self, button):
        """Manual pool scrape trigger"""
        threading.Thread(target=self.scrape_pool, daemon=True).start()
    
    def update_smart_status(self):
        """Update smart coordinator status display"""
        stats = self.scan_db.get_stats()
        
        self.pool_exclusions_value.set_text(f"{stats['pool_blocks']} blocks")
        self.my_blocks_value.set_text(f"{stats['my_blocks']} blocks")
        
        if self.last_pool_scrape:
            last_scrape = datetime.fromtimestamp(self.last_pool_scrape)
            self.last_scrape_value.set_text(last_scrape.strftime("%H:%M:%S"))
            
            next_scrape = last_scrape + timedelta(seconds=self.scrape_interval)
            self.next_scrape_value.set_text(next_scrape.strftime("%H:%M:%S"))
    
    def load_previous_state(self):
        """Load previous session state"""
        state = self.state_mgr.load_state()
        
        if state:
            self.log("=" * 60, "info")
            self.log("📁 PREVIOUS SESSION DETECTED", "success")
            self.log("=" * 60, "info")
            self.log(f"   Last run: {state.get('timestamp', 'Unknown')}", "info")
            self.log(f"   Block index: #{state.get('current_block_index', 0)}", "info")
            self.log(f"   Keys checked: {state.get('keys_checked', 0):,}", "info")
            self.log(f"   Range: {state.get('range_start', 'N/A')} → {state.get('range_end', 'N/A')}", "info")
            self.log("", "info")
            self.log("🎯 Click 'Start' to resume from where you left off!", "success")
            self.log("=" * 60, "info")
            
            # Restore state
            self.current_block_index = state.get('current_block_index', 0)
            self.keys_checked = state.get('keys_checked', 0)
            
            # Update UI
            if 'range_start' in state:
                self.range_start.set_text(state['range_start'])
            if 'range_end' in state:
                self.range_end.set_text(state['range_end'])
            
            # Update probability dashboard with loaded state
            GLib.timeout_add(1000, self.update_probability_dashboard)
        else:
            self.log("ℹ️  No previous session found - starting fresh", "info")
    
    def save_current_state(self):
        """Save current state for resume"""
        state = {
            'current_block_index': self.current_block_index,
            'keys_checked': self.keys_checked,
            'range_start': self.range_start.get_text(),
            'range_end': self.range_end.get_text(),
            'timestamp': datetime.now().isoformat()
        }
        
        if self.state_mgr.save_state(state):
            self.log("💾 State saved successfully", "success")
        else:
            self.log("⚠ Failed to save state", "warning")
    
    def populate_blocks_view(self):
        """Populate block manager view with current data"""
        if not self.block_mgr:
            return False
        
        # Update stats
        total_blocks = self.block_mgr.total_blocks
        my_completed = len(self.scan_db.conn.execute('SELECT * FROM my_scanned').fetchall())
        pool_scanned = len(self.scan_db.conn.execute('SELECT * FROM pool_scanned').fetchall())
        remaining = total_blocks - my_completed - pool_scanned
        
        self.total_blocks_label.set_text(f"{total_blocks:,}")
        self.remaining_blocks_label.set_text(f"{remaining:,}")
        
        # Clear and populate TreeView
        self.block_store.clear()
        
        # Show blocks around current position (40 blocks: 20 before, current, 19 after)
        start_index = max(0, self.current_block_index - 20)
        end_index = min(self.block_mgr.total_blocks, self.current_block_index + 20)
        
        for i in range(start_index, end_index):
            block = self.block_mgr.get_block(i)
            scanned, by_whom = self.scan_db.is_block_scanned(block[0], block[1])
            
            # Calculate block size
            block_size = block[1] - block[0] + 1
            
            # Determine status
            if scanned:
                status = f"✅ Done ({by_whom})"
            elif i == self.current_block_index:
                status = "⚙️ Current"
            else:
                status = "⏳ Pending"
            
            # Add to store: index, start_hex, end_hex, size, status, start_int, end_int (hidden)
            self.block_store.append([
                i,
                f"0x{block[0]:X}",
                f"0x{block[1]:X}",
                f"{block_size:,}",
                status,
                f"{block[0]:X}",  # Hidden: for operations
                f"{block[1]:X}"   # Hidden: for operations
            ])
        
        return False
    
    
    def populate_exclusions_view(self):
        """Populate exclusions view with scanned ranges"""
        buffer = self.exclusions_view.get_buffer()
        
        # Get actual stats
        stats = self.scan_db.get_stats()
        
        text = "EXCLUDED RANGES\n"
        text += "=" * 80 + "\n"
        text += f"📊 CURRENT STATUS (from database):\n"
        text += f"   Pool Exclusions: {stats['pool_blocks']} blocks\n"
        text += f"   My Completed: {stats['my_blocks']} blocks\n"
        text += f"   Total: {stats['total_blocks']} blocks\n"
        text += "=" * 80 + "\n\n"
        
        # My scanned blocks
        text += "MY SCANNED BLOCKS:\n"
        text += "-" * 80 + "\n"
        cursor = self.scan_db.conn.cursor()
        cursor.execute('SELECT * FROM my_scanned ORDER BY block_start')
        my_blocks = cursor.fetchall()
        
        for block in my_blocks:  # Show ALL blocks
            # block[0] and block[1] are already hex strings, block[3] is keys_checked
            text += f"0x{block[0]} → 0x{block[1]} (Keys: {block[3]:,})\n"
        
        text += f"\nTotal my blocks: {len(my_blocks)} (should match {stats['my_blocks']} above)\n\n"
        
        # Pool scanned blocks
        text += "POOL SCANNED BLOCKS:\n"
        text += "-" * 80 + "\n"
        cursor.execute('SELECT * FROM pool_scanned ORDER BY block_start')
        pool_blocks = cursor.fetchall()
        
        for block in pool_blocks:  # Show ALL blocks
            # block[0] and block[1] are already hex strings
            text += f"0x{block[0]} → 0x{block[1]}\n"
        
        text += f"\nTotal pool blocks: {len(pool_blocks)} (should match {stats['pool_blocks']} above)\n"
        
        if len(pool_blocks) != stats['pool_blocks']:
            text += f"\n⚠️ WARNING: Mismatch! List shows {len(pool_blocks)} but stats show {stats['pool_blocks']}\n"
            text += f"   This might indicate duplicate entries or database corruption.\n"
        
        buffer.set_text(text)
        return False
    
    def on_block_right_click(self, widget, event):
        """Handle right-click on block row"""
        if event.button == 3:  # Right click
            # Get clicked row
            path_info = widget.get_path_at_pos(int(event.x), int(event.y))
            if path_info is None:
                return False
            
            path, column, cell_x, cell_y = path_info
            widget.set_cursor(path, column, False)
            
            # Get row data
            model = widget.get_model()
            iter = model.get_iter(path)
            block_index = model.get_value(iter, 0)
            block_start = model.get_value(iter, 5)  # Hidden column with int value
            block_end = model.get_value(iter, 6)    # Hidden column with int value
            
            # Create context menu
            menu = Gtk.Menu()
            
            # Rescan option
            rescan_item = Gtk.MenuItem(label="🔄 Rescan This Block")
            rescan_item.connect("activate", self.on_rescan_block, block_index, block_start, block_end)
            menu.append(rescan_item)
            
            # Delete option
            delete_item = Gtk.MenuItem(label="🗑️ Delete from Database")
            delete_item.connect("activate", self.on_delete_block, block_index, block_start, block_end)
            menu.append(delete_item)
            
            menu.show_all()
            menu.popup(None, None, None, None, event.button, event.time)
            
            return True
        return False
    
    def on_rescan_block(self, widget, block_index, block_start_hex, block_end_hex):
        """Load block into configuration for rescanning"""
        # Convert hex strings to int
        block_start = int(block_start_hex, 16) if isinstance(block_start_hex, str) else block_start_hex
        block_end = int(block_end_hex, 16) if isinstance(block_end_hex, str) else block_end_hex
        
        # Set range in ACTUAL scan inputs (not default config)
        # Find the actual range input fields in Configuration tab
        if hasattr(self, 'manual_start_entry') and hasattr(self, 'manual_end_entry'):
            # Use manual range entries if they exist
            self.manual_start_entry.set_text(f"0x{block_start:X}")
            self.manual_end_entry.set_text(f"0x{block_end:X}")
        else:
            # Fallback to range_start/end but warn user
            self.range_start.set_text(f"0x{block_start:X}")
            self.range_end.set_text(f"0x{block_end:X}")
            self.log("⚠️ Range set in config. This will change your default range!", "warning")
        
        # Delete from database
        cursor = self.scan_db.conn.cursor()
        cursor.execute('DELETE FROM my_scanned WHERE block_start = ?', (f"{block_start:X}",))
        self.scan_db.conn.commit()
        self.cache_dirty = True
        
        # Clear state file so block starts from 0%
        if (self.current_block and 
            block_start == self.current_block[0] and 
            block_end == self.current_block[1]):
            self.state_mgr.clear_state()
            self.keys_checked = 0
        
        self.log(f"✅ Block #{block_index} loaded for rescan: 0x{block_start:X} → 0x{block_end:X}", "success")
        self.log("   Deleted from completed blocks + cleared progress", "info")
        self.log("   Click 'Start' to rescan from 0%", "info")
        
        # Refresh block list
        self.populate_blocks_view()
        
        # Switch to Configuration tab
        notebook = self.get_children()[0]  # Main notebook
        notebook.set_current_page(0)  # Configuration tab
    
    def on_delete_block(self, widget, block_index, block_start_hex, block_end_hex):
        """Delete block from database with confirmation"""
        # Convert hex strings to int
        block_start = int(block_start_hex, 16) if isinstance(block_start_hex, str) else block_start_hex
        block_end = int(block_end_hex, 16) if isinstance(block_end_hex, str) else block_end_hex
        
        # Confirmation dialog
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.YES_NO,
            text="Delete Block?"
        )
        dialog.format_secondary_text(
            f"Are you sure you want to delete block #{block_index}?\n\n"
            f"Range: 0x{block_start:X} → 0x{block_end:X}\n\n"
            f"This will remove it from your completed blocks."
        )
        
        response = dialog.run()
        dialog.destroy()
        
        if response == Gtk.ResponseType.YES:
            # Delete from database
            cursor = self.scan_db.conn.cursor()
            cursor.execute('DELETE FROM my_scanned WHERE block_start = ?', (f"{block_start:X}",))
            self.scan_db.conn.commit()
            self.cache_dirty = True
            
            # IMPORTANT: Clear state file if this is the current block
            # This ensures the block starts from 0% when rescanned
            if (self.current_block and 
                block_start == self.current_block[0] and 
                block_end == self.current_block[1]):
                self.state_mgr.clear_state()
                self.keys_checked = 0  # Reset progress
                self.log("🔄 State file cleared - block will start from 0%", "info")
            
            self.log(f"🗑️ Deleted block #{block_index} from database", "warning")
            self.log(f"   Block is now marked as unscanned", "info")
            
            # Refresh block list
            self.populate_blocks_view()
            
            # Update visualization
            if self.progress_drawing:
                self.progress_drawing.queue_draw()
    
    def on_refresh_blocks(self, button):
        """Refresh block list"""
        self.populate_blocks_view()
        self.log("🔄 Block list refreshed", "success")
    
    def on_refresh_exclusions(self, button):
        """Refresh exclusion list"""
        self.populate_exclusions_view()
        self.log("🔄 Exclusion list refreshed", "success")
    
    def show_match_alert(self, match_line):
        """Show BIG alert when a match is found! 🎉"""
        import subprocess
        
        # Play system beep (multiple times!)
        for _ in range(5):
            try:
                subprocess.run(['paplay', '/usr/share/sounds/freedesktop/stereo/complete.oga'], 
                             capture_output=True, timeout=1)
            except:
                try:
                    # Fallback: terminal bell
                    print('\a' * 10)  # System beep
                except:
                    pass
        
        # Create popup dialog
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text="🎉🎉🎉 MATCH FOUND! 🎉🎉🎉"
        )
        
        dialog.format_secondary_markup(
            f"<span size='large' weight='bold' foreground='#4CAF50'>"
            f"KEY DISCOVERED!\n\n"
            f"</span>"
            f"<span foreground='#FF9800'>{match_line}</span>\n\n"
            f"<span size='small' foreground='#2196F3'>✅ Scanning automatically stopped</span>\n"
            f"<span size='small'>Check Found.txt for full details!</span>"
        )
        
        # Make dialog stay on top and grab attention
        dialog.set_keep_above(True)
        dialog.set_urgency_hint(True)
        
        dialog.run()
        dialog.destroy()
        
        # Also log prominently
        self.log("="*60, "match")
        self.log("🎉🎉🎉 JACKPOT! KEY FOUND! 🎉🎉🎉", "match")
        self.log(f"Details: {match_line}", "match")
        self.log("="*60, "match")
    
    def on_start(self, button):
        """Start searching"""
        # GUARD: Prevent double-start
        if self.is_running:
            self.log("⚠️ Already running, ignoring duplicate start", "warning")
            return
        
        # Initialize block manager
        try:
            range_start = int(self.range_start.get_text(), 16)
            range_end = int(self.range_end.get_text(), 16)
            block_size = int(self.block_size.get_text(), 16)
            
            self.block_mgr = BlockManager(range_start, range_end, block_size)
            self.range_start_value = range_start
            self.range_end_value = range_end
            self.total_keys_in_range = range_end - range_start + 1
            
            # DIAGNOSTIC LOGGING
            self.log("=" * 60, "info")
            self.log("📊 BLOCK SIZE DIAGNOSTIC", "success")
            self.log("=" * 60, "info")
            self.log(f"Block Size (hex): 0x{block_size:X}", "info")
            self.log(f"Block Size (dec): {block_size:,} keys", "info")
            self.log(f"Block Size (bits): {block_size.bit_length()} bits", "info")
            
            # Calculate expected time
            estimated_speed = 226_000_000  # 226 Mk/s
            estimated_time_sec = block_size / estimated_speed
            estimated_time_min = estimated_time_sec / 60
            
            self.log(f"Expected Speed: {estimated_speed:,} keys/sec (226 Mk/s)", "info")
            self.log(f"Expected Time: {estimated_time_sec:.1f} seconds ({estimated_time_min:.2f} minutes)", "warning")
            self.log("=" * 60, "info")
            
            self.log(f"📊 Range initialized: {self.block_mgr.total_blocks} blocks", "success")
            
        except Exception as e:
            self.log(f"❌ Error initializing range: {e}", "error")
            return
        
        # SET RUNNING FLAG FIRST!
        self.is_running = True
        self.start_time = datetime.now()
        
        # Find next unscanned block (this will start the thread)
        self.find_next_block()
        
        if self.current_block is None:
            self.log("✅ All blocks scanned!", "success")
            self.is_running = False
            return
        
        # Refresh block cache for visualizations
        self.refresh_block_cache()
        
        # Disable both sets of start buttons
        self.start_btn.set_sensitive(False)
        self.start_btn_config.set_sensitive(False)
        
        # Enable both sets of pause/stop buttons
        self.pause_btn.set_sensitive(True)
        self.pause_btn_config.set_sensitive(True)
        self.stop_btn.set_sensitive(True)
        self.stop_btn_config.set_sensitive(True)
        
        self.log("🚀 Starting search...", "success")
        
        # NOTE: find_next_block() already started the thread, don't start again!
        
        # Start runtime timer
        GLib.timeout_add(1000, self.update_runtime)
    
    def find_next_block(self):
        """Find next unscanned block (yields to UI every 100 blocks)"""
        checks_per_batch = 100  # Check max 100 blocks before yielding to UI
        checks_done = 0
        
        while self.current_block_index < self.block_mgr.total_blocks:
            block = self.block_mgr.get_block(self.current_block_index)
            scanned, by_whom = self.scan_db.is_block_scanned(block[0], block[1])
            
            # Check if already scanned
            if scanned:
                self.current_block_index += 1
                checks_done += 1
                
                # Yield to UI every N blocks to prevent freeze
                if checks_done >= checks_per_batch:
                    self.log(f"🔍 Checked {checks_done} blocks, continuing search...", "info")
                    GLib.timeout_add(10, self.find_next_block)  # Continue after 10ms
                    return
                continue
            
            # Check pattern exclusions
            skip_pattern, pattern_reason = self.should_skip_block_by_pattern(block[0], block[1])
            if skip_pattern:
                self.current_block_index += 1
                checks_done += 1
                
                # Yield to UI every N blocks to prevent freeze
                if checks_done >= checks_per_batch:
                    self.log(f"🔍 Checked {checks_done} blocks (skipped {pattern_reason}), continuing...", "info")
                    GLib.timeout_add(10, self.find_next_block)  # Continue after 10ms
                    return
                continue
            
            # Block is good - use it!
            self.current_block = block
            self.keys_checked = 0  # Reset progress for new block
            self.log(f"📍 Next block: #{self.current_block_index} ({hex(block[0])} - {hex(block[1])})", "info")
            self.block_value.set_text(f"#{self.current_block_index}")
            
            # Start the search thread
            thread = threading.Thread(target=self.run_block_search, daemon=True)
            thread.start()
            return
        
        # Reached end of blocks
        self.current_block = None
        self.log("✅ All blocks scanned!", "success")
        self.is_running = False
    
    def run_block_search(self):
        """Search current block"""
        if not self.current_block:
            return
        
        block_start, block_end = self.current_block
        
        # Reset session counter (keys_checked already has previous progress)
        self.session_keys = 0
        
        # Build KeyHunt command for this block
        cmd = self.build_keyhunt_command(block_start, block_end)
        
        keyhunt_error = False  # Track if KeyHunt had errors
        lines_read = 0  # Count lines read
        
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            for line in iter(self.process.stdout.readline, ''):
                if not self.is_running or self.is_paused:
                    break
                
                line = line.strip()
                if line:
                    lines_read += 1
                    
                    # CRITICAL: Errors and matches
                    if 'Wrong args' in line or 'ERROR' in line or 'Error:' in line:
                        keyhunt_error = True
                        GLib.idle_add(self.log, f"🚨 ERROR: {line}", "error")
                    elif 'PubAddress:' in line or 'Priv' in line:
                        self.matches_found += 1
                        GLib.idle_add(self.matches_value.set_text, str(self.matches_found))
                        GLib.idle_add(self.log, f"🎉 MATCH: {line}", "match")
                        
                        # 🎉 JACKPOT ALERT! 🎉
                        GLib.idle_add(self.show_match_alert, line)
                        
                        # 🛑 AUTO-STOP: We found it! Stop searching!
                        self.log("🛑 AUTO-STOPPING: Match found!", "success")
                        self.is_running = False
                        if self.process:
                            self.process.terminate()
                    else:
                        # Parse speed and keys
                        speed_match = re.search(r'([\d.]+)\s*Mk/s', line)
                        if speed_match:
                            speed = float(speed_match.group(1))
                            GLib.idle_add(self.speed_value.set_text, f"{speed:.2f} Mk/s")
                        
                        keys_match = re.search(r'T:\s*([\d,]+)', line)
                        if keys_match:
                            keys_str = keys_match.group(1).replace(',', '')
                            self.session_keys = int(keys_str)
                            
                            # Display total progress (previous + current session)
                            total_keys = self.keys_checked + self.session_keys
                            GLib.idle_add(self.keys_value.set_text, f"{total_keys:,}")
                            
                            # Update current block progress bar
                            if self.current_block:
                                block_start, block_end = self.current_block
                                keys_in_block = block_end - block_start + 1
                                progress = min(1.0, total_keys / keys_in_block)
                                
                                GLib.idle_add(self.current_block_progressbar.set_fraction, progress)
                                GLib.idle_add(self.current_block_progressbar.set_text, f"{progress * 100:.2f}%")
                                
                                # Update stats
                                remaining = keys_in_block - total_keys
                                eta_seconds = remaining / (self.current_speed * 1_000_000) if self.current_speed > 0 else 0
                                eta_minutes = eta_seconds / 60
                                
                                stats_text = (
                                    f"<span size='small'>"
                                    f"Checked: <b>{total_keys:,}</b> / {keys_in_block:,} keys | "
                                    f"Remaining: <b>{remaining:,}</b> | "
                                    f"ETA: <b>{eta_minutes:.1f} min</b>"
                                    f"</span>"
                                )
                                GLib.idle_add(self.current_block_stats.set_markup, stats_text)
                            
                            # AUTO-STOP: Check if we've completed the block
                            if self.current_block:
                                block_start, block_end = self.current_block
                                keys_in_block = block_end - block_start + 1
                                
                                # If total keys checked >= block size, we're done!
                                if total_keys >= keys_in_block:
                                    self.log(f"✅ Block complete! Checked {total_keys:,} / {keys_in_block:,} keys", "success")
                                    self.is_running = False
                                    if self.process:
                                        self.process.terminate()
                                    # Will be marked complete after process exits
                        
                        # LOG: Only log lines with speed data (every 2 seconds)
                        if 'Mk/s' in line or 'GPU' in line or 'Start' in line:
                            GLib.idle_add(self.log, line, "info")
            
            # Wait for process to actually exit
            if self.process:
                try:
                    self.process.wait(timeout=5)
                    exit_code = self.process.returncode
                except subprocess.TimeoutExpired:
                    GLib.idle_add(self.log, "⏱️ Process timeout waiting for exit", "warning")
                    exit_code = -1
            else:
                exit_code = -1  # Process was terminated
            
            GLib.idle_add(self.log, f"🔍 Process exited: code={exit_code}, lines={lines_read}, errors={keyhunt_error}", "info")
            
            # Only mark block complete if:
            # 1. No errors detected
            # 2. Not manually paused (is_paused = False)
            # 3. Read at least 10 lines of output (not just help text)
            # NOTE: We allow exit_code -15 (SIGTERM) because we auto-terminate when block completes
            if (not self.is_paused and 
                not keyhunt_error and 
                (exit_code == 0 or exit_code == -15) and  # Allow our own termination
                lines_read >= 10):
                GLib.idle_add(self.on_block_completed)
            else:
                reason = []
                if self.is_paused:
                    reason.append("PAUSED")
                if keyhunt_error:
                    reason.append("ERROR DETECTED")
                if exit_code not in [0, -15]:
                    reason.append(f"EXIT CODE {exit_code}")
                if lines_read < 10:
                    reason.append(f"TOO FEW LINES ({lines_read})")
                
                # Check if this is a startup failure (GPU might be busy from orphaned process)
                startup_failure = (exit_code == -1 and lines_read == 0)
                
                if startup_failure and not hasattr(self, 'retry_count'):
                    self.retry_count = 0
                
                if startup_failure and self.retry_count < 3:
                    self.retry_count += 1
                    GLib.idle_add(self.log, f"⚠️ Block start failed (attempt {self.retry_count}/3) - GPU might be busy", "warning")
                    GLib.idle_add(self.log, f"🔄 Retrying in 3 seconds...", "info")
                    time.sleep(3)
                    # Retry the same block
                    thread = threading.Thread(target=self.run_block_search, daemon=True)
                    thread.start()
                else:
                    # Real failure or max retries
                    self.retry_count = 0
                    GLib.idle_add(self.log, f"❌ Block NOT completed: {', '.join(reason)}", "error")
                    GLib.idle_add(self.log, "🛑 STOPPING - Fix the issue before restarting!", "error")
                    self.is_running = False
            
        except Exception as e:
            GLib.idle_add(self.log, f"❌ Exception: {e}", "error")
            self.is_running = False
    
    def on_block_completed(self):
        """Handle block completion"""
        # Reset retry counter on successful completion
        self.retry_count = 0
        
        if self.current_block:
            # Calculate total keys checked (previous + this session)
            total_keys_checked = self.keys_checked + self.session_keys
            
            self.scan_db.add_my_block(
                self.current_block[0],
                self.current_block[1],
                total_keys_checked
            )
            self.cache_dirty = True  # Refresh cache on next redraw
            
            self.log(f"✅ Block #{self.current_block_index} completed! ({total_keys_checked:,} keys)", "success")
            self.update_smart_status()
            
            # Update probability dashboard after completing a block
            self.update_probability_dashboard()
            
            # Move to next block
            self.current_block_index += 1
            self.keys_checked = 0
            
            # Find next block
            self.find_next_block()
            
            if self.current_block:
                # CRITICAL: Terminate old process before starting new block
                if self.process:
                    try:
                        self.process.terminate()
                        self.process.wait(timeout=5)
                        self.log("🛑 Previous block process terminated", "info")
                    except:
                        try:
                            self.process.kill()
                            self.log("🛑 Previous block process killed (forced)", "warning")
                        except:
                            pass
                    self.process = None
                
                # Small delay to ensure GPU is freed
                time.sleep(2)
                
                # Continue with next block
                thread = threading.Thread(target=self.run_block_search, daemon=True)
                thread.start()
            else:
                self.log("🎉 ALL BLOCKS COMPLETED!", "success")
                self.on_stop(None)
    
    def on_pause(self, button):
        """Pause searching"""
        if self.is_running and not self.is_paused:
            self.is_paused = True
            self.pause_btn.set_label("▶ Resume")
            self.pause_btn_config.set_label("▶ Resume")
            
            # Add session keys to total before saving
            self.keys_checked += self.session_keys
            
            if self.process:
                self.process.terminate()
            
            self.save_current_state()
            self.log(f"⏸ Paused - Progress saved: {self.keys_checked:,} keys", "warning")
        else:
            self.is_paused = False
            self.pause_btn.set_label("⏸ Pause")
            self.pause_btn_config.set_label("⏸ Pause")
            self.log("▶ Resuming...", "success")
            
            thread = threading.Thread(target=self.run_block_search, daemon=True)
            thread.start()
    
    def on_stop(self, button):
        """Stop searching"""
        self.is_running = False
        self.is_paused = False
        
        if self.process:
            self.process.terminate()
            self.process = None
        
        self.save_current_state()
        
        # Enable both start buttons
        self.start_btn.set_sensitive(True)
        self.start_btn_config.set_sensitive(True)
        
        # Disable both pause/stop buttons
        self.pause_btn.set_sensitive(False)
        self.pause_btn_config.set_sensitive(False)
        self.stop_btn.set_sensitive(False)
        self.stop_btn_config.set_sensitive(False)
        
        # Reset pause button labels
        self.pause_btn.set_label("⏸ Pause")
        self.pause_btn_config.set_label("⏸ Pause")
        
        self.log("⏹ Stopped - State saved", "warning")
    
    def on_window_close(self, widget, event):
        """Handle window close"""
        if self.is_running or self.current_block_index > 0:
            # Save state
            self.save_current_state()
            self.log("", "info")
            self.log("=" * 60, "success")
            self.log("💾 STATE SAVED - SAFE TO CLOSE", "success")
            self.log("=" * 60, "success")
            self.log(f"   Block index saved: #{self.current_block_index}", "info")
            self.log(f"   Keys checked saved: {self.keys_checked:,}", "info")
            self.log("", "info")
            self.log("🎯 Next time you open: Click 'Start' to resume!", "success")
            self.log("=" * 60, "success")
            
            # Give user time to see the message
            import time
            time.sleep(1)
        
        self.scan_db.close()
        return False
    
    def build_keyhunt_command(self, block_start, block_end):
        """Build KeyHunt command for specific block"""
        keyhunt_bin = self.keyhunt_path.get_text()
        
        # Calculate where to actually start from (resume point)
        # If we've already checked some keys, start from where we left off
        actual_start = block_start
        if self.keys_checked > 0:
            # Calculate resume position
            actual_start = block_start + self.keys_checked
            
            # Make sure we don't go past the block end
            if actual_start > block_end:
                actual_start = block_end
            
            self.log(f"📍 Resuming from 0x{actual_start:X} (skipped {self.keys_checked:,} keys)", "info")
        
        # Calculate remaining keys to search
        key_count = block_end - actual_start + 1
        
        cmd = [keyhunt_bin]
        cmd.extend(['-t', '0'])  # CPU threads: 0 (GPU only)
        cmd.append('-g')         # Enable GPU mode
        cmd.extend(['--gpui', self.gpu_id.get_text()])  # GPU device ID
        cmd.extend(['--gpux', '256,256'])  # GPU grid configuration
        cmd.extend(['-m', 'address'])      # Mode: address matching
        cmd.extend(['--coin', 'BTC'])      # Bitcoin network
        
        # CLOSED RANGE with start and end for automatic block completion
        # KeyHunt will stop when it reaches block_end
        cmd.extend(['--range', f'{hex(actual_start)[2:]}:{hex(block_end)[2:]}'])
        
        cmd.extend(['-o', 'Found.txt'])    # Output file
        cmd.append(self.target_entry.get_text())  # Target address (MUST BE LAST!)
        
        # Log the actual command for debugging
        self.log(f"📌 Command: {' '.join(cmd)}", "info")
        self.log(f"📊 Block range: 0x{actual_start:X} to 0x{block_end:X}", "info")
        keys_to_search = block_end - actual_start + 1
        self.log(f"🔢 Keys to search: {keys_to_search:,} ({keys_to_search / 1e12:.2f} trillion)", "info")
        
        return cmd
    
    def update_buttons(self):
        """Update button states based on current status"""
        if self.is_running and not self.is_paused:
            # Running
            self.start_btn.set_sensitive(False)
            self.start_btn_config.set_sensitive(False)
            self.pause_btn.set_sensitive(True)
            self.pause_btn_config.set_sensitive(True)
            self.stop_btn.set_sensitive(True)
            self.stop_btn_config.set_sensitive(True)
        elif self.is_paused:
            # Paused
            self.start_btn.set_sensitive(False)
            self.start_btn_config.set_sensitive(False)
            self.pause_btn.set_sensitive(True)
            self.pause_btn_config.set_sensitive(True)
            self.stop_btn.set_sensitive(True)
            self.stop_btn_config.set_sensitive(True)
        else:
            # Stopped
            self.start_btn.set_sensitive(True)
            self.start_btn_config.set_sensitive(True)
            self.pause_btn.set_sensitive(False)
            self.pause_btn_config.set_sensitive(False)
            self.stop_btn.set_sensitive(False)
            self.stop_btn_config.set_sensitive(False)
        return False
    
    def process_output_line(self, line):
        """Process KeyHunt output"""
        # Check for CRITICAL ERRORS that mean search isn't working
        if 'Wrong args' in line or 'ERROR' in line or 'Error:' in line:
            self.log(f"❌ KEYHUNT ERROR: {line}", "error")
            self.log("🚨 CRITICAL: KeyHunt rejected command!", "error")
            self.log("🚨 Stopping - FIX COMMAND BEFORE CONTINUING!", "error")
            # Stop immediately - don't mark block as complete!
            self.is_running = False
            if self.process:
                self.process.terminate()
            GLib.idle_add(self.update_buttons)
            return
        
        # Ignore help text
        if any(x in line for x in ['--help', '-h,', 'OPTIONS', 'KeyHunt-Cuda', 'TARGETS']):
            return  # Skip help output
        
        # Check for help output (means command failed)
        if 'KeyHunt-Cuda [OPTIONS...]' in line or '--help' in line:
            self.log("🚨 KeyHunt showing help - command rejected!", "error")
            return
        
        # Check for match
        if 'PubAddress:' in line or 'Priv' in line:
            self.matches_found += 1
            self.matches_value.set_text(str(self.matches_found))
            self.log(line, "match")
            return
        
        # Parse speed
        speed_match = re.search(r'([\d.]+)\s*[MK]k/s', line)
        if speed_match:
            self.current_speed = float(speed_match.group(1))
            self.speed_value.set_text(f"{self.current_speed:.2f} Mk/s")
        
        # Parse keys checked
        keys_match = re.search(r'T:\s*([\d,]+)', line)
        if keys_match:
            keys_str = keys_match.group(1).replace(',', '')
            self.keys_checked = int(keys_str)
            self.keys_value.set_text(self.format_number(self.keys_checked))
            
            # Check if we've reached the block end (for open-ended searches)
            if self.current_block and self.keys_checked > 0:
                block_start, block_end = self.current_block
                keys_to_search = block_end - block_start + 1
                
                # If we've checked enough keys, stop and complete the block
                if self.keys_checked >= keys_to_search:
                    self.log(f"✅ Block complete! Searched {self.keys_checked:,} keys", "success")
                    self.is_running = False
                    if self.process:
                        self.process.terminate()
                    GLib.idle_add(self.on_block_completed)
                    return
            
            # Update progress
            if self.total_keys_in_range > 0:
                percentage = (self.keys_checked / self.total_keys_in_range) * 100
                if percentage < 0.0001:
                    percent_str = f"{percentage:.7f}%"
                else:
                    percent_str = f"{percentage:.4f}%"
                self.progress_value.set_text(percent_str)
        
        # Log
        if 'ERROR' in line or 'error' in line:
            self.log(line, "error")
        elif 'GPU' in line or 'CUDA' in line:
            self.log(line, "success")
        else:
            self.log(line, "info")
    
    def update_runtime(self):
        """Update runtime display"""
        if not self.is_running or not self.start_time:
            return False
        
        elapsed = datetime.now() - self.start_time
        hours, remainder = divmod(int(elapsed.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        
        self.runtime_value.set_text(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
        
        # Auto-save state every 5 minutes
        if minutes % 5 == 0 and seconds == 0:
            self.save_current_state()
            self.log("💾 Auto-saved progress", "success")
        
        # Update visual progress bar every 5 seconds
        if seconds % 5 == 0:
            if self.progress_drawing:
                self.progress_drawing.queue_draw()
            # Update probability dashboard
            self.update_probability_dashboard()
        
        return True
    
    def format_number(self, num):
        """Format large numbers"""
        if num >= 1e12:
            return f"{num / 1e12:.2f} T"
        elif num >= 1e9:
            return f"{num / 1e9:.2f} B"
        elif num >= 1e6:
            return f"{num / 1e6:.2f} M"
        return str(num)
    
    def get_current_puzzle_number(self):
        """Get currently selected puzzle number"""
        text = self.puzzle_combo.get_active_text()
        if text:
            # Extract number from "#71 - 71 bits - 7.1 BTC"
            import re
            match = re.match(r'#(\d+)', text)
            if match:
                return int(match.group(1))
        return 71  # Default
    
    def on_puzzle_changed(self, combo):
        """Handle puzzle selection change"""
        text = combo.get_active_text()
        if not text:
            return
        
        # Extract puzzle number
        puzzle_num = int(text.split('#')[1].split(' ')[0])
        
        # Update info label
        preset = self.PUZZLE_PRESETS[puzzle_num]
        self.puzzle_info_label.set_markup(
            f"<span size='small'>Selected: {preset['name']} - {preset['bits']} bits - Reward: {preset['reward']}</span>"
        )
        self.db_info_label.set_markup(
            f"<span size='small' foreground='#CCCCCC'>Database: scan_data_puzzle_{puzzle_num}.db</span>"
        )
    
    def calculate_discovery_probability(self):
        """Calculate overall probability of discovering the key"""
        if not self.block_mgr:
            return 0.0
        
        # Factor 1: Search Space Coverage (0-40 points)
        total_blocks = self.block_mgr.total_blocks
        my_completed = len(self.scan_db.conn.execute('SELECT * FROM my_scanned').fetchall())
        coverage_percent = (my_completed / total_blocks * 100) if total_blocks > 0 else 0
        factor1_score = min(coverage_percent * 0.4, 40)  # Cap at 40 points
        
        # Factor 2: Pattern Optimization (0-20 points)
        factor2_score = 0
        if hasattr(self, 'exclude_iter3') and self.exclude_iter3.get_active():
            factor2_score += 12  # High confidence in this pattern
        if hasattr(self, 'exclude_iter4') and self.exclude_iter4.get_active():
            factor2_score += 5
        if hasattr(self, 'exclude_alphanum') and self.exclude_alphanum.get_active():
            factor2_score += 3
        
        # Factor 3: Pool Coordination (0-15 points)
        pool_count = len(self.scan_db.conn.execute('SELECT * FROM pool_scanned').fetchall())
        pool_coverage = (pool_count / total_blocks * 100) if total_blocks > 0 else 0
        # Good if pool has high coverage (less competition)
        factor3_score = min(pool_coverage * 0.15, 15)
        
        # Factor 4: Search Speed (0-15 points)
        speed_mks = 0
        if hasattr(self, 'speed_value'):
            speed_text = self.speed_value.get_text()
            try:
                speed_mks = float(speed_text.replace('Mk/s', '').strip())
            except:
                speed_mks = 0
        
        # Score based on speed (>200 Mk/s is good GPU)
        if speed_mks > 200:
            factor4_score = 15
        elif speed_mks > 100:
            factor4_score = 10
        elif speed_mks > 50:
            factor4_score = 5
        else:
            factor4_score = 0
        
        # Factor 5: Time Investment (0-10 points)
        runtime_seconds = 0
        if self.start_time:
            runtime_seconds = (datetime.now() - self.start_time).total_seconds()
        
        # Score based on time (more time = more probability)
        hours = runtime_seconds / 3600
        if hours > 100:
            factor5_score = 10
        elif hours > 24:
            factor5_score = 8
        elif hours > 10:
            factor5_score = 6
        elif hours > 1:
            factor5_score = 3
        else:
            factor5_score = 1
        
        # Total probability (0-100)
        total_probability = factor1_score + factor2_score + factor3_score + factor4_score + factor5_score
        
        return min(total_probability, 100)
    
    def update_probability_dashboard(self):
        """Update probability dashboard with current stats"""
        if not self.block_mgr:
            return
        
        # Calculate factors
        total_blocks = self.block_mgr.total_blocks
        my_completed = len(self.scan_db.conn.execute('SELECT * FROM my_scanned').fetchall())
        pool_count = len(self.scan_db.conn.execute('SELECT * FROM pool_scanned').fetchall())
        
        coverage_percent = (my_completed / total_blocks * 100) if total_blocks > 0 else 0
        pool_coverage = (pool_count / total_blocks * 100) if total_blocks > 0 else 0
        
        # Factor 1: Search Space Coverage
        factor1_score = min(coverage_percent * 0.4, 40)
        self.prob_factor1_value.set_markup(
            f"<span foreground='#4CAF50'>{coverage_percent:.4f}% of keyspace</span>"
        )
        self.prob_factor1_impact.set_markup(
            f"<span size='small' foreground='#4CAF50'>+{factor1_score:.2f}%</span>"
        )
        
        # Factor 2: Pattern Optimization
        pattern_active = []
        factor2_score = 0
        if hasattr(self, 'exclude_iter3') and self.exclude_iter3.get_active():
            pattern_active.append("Iter3")
            factor2_score += 12
        if hasattr(self, 'exclude_iter4') and self.exclude_iter4.get_active():
            pattern_active.append("Iter4")
            factor2_score += 5
        if hasattr(self, 'exclude_alphanum') and self.exclude_alphanum.get_active():
            pattern_active.append("AlphaNum")
            factor2_score += 3
        
        if pattern_active:
            self.prob_factor2_value.set_markup(
                f"<span foreground='#4CAF50'>{', '.join(pattern_active)} active</span>"
            )
            self.prob_factor2_impact.set_markup(
                f"<span size='small' foreground='#4CAF50'>+{factor2_score:.2f}%</span>"
            )
        else:
            self.prob_factor2_value.set_markup("<span foreground='#FF9800'>None active</span>")
            self.prob_factor2_impact.set_markup("<span size='small' foreground='#CCCCCC'>+0.00%</span>")
        
        # Factor 3: Pool Coordination
        factor3_score = min(pool_coverage * 0.15, 15)
        if pool_count > 0:
            self.prob_factor3_value.set_markup(
                f"<span foreground='#4CAF50'>{pool_coverage:.2f}% pool coverage</span>"
            )
            self.prob_factor3_impact.set_markup(
                f"<span size='small' foreground='#4CAF50'>+{factor3_score:.2f}%</span>"
            )
        else:
            self.prob_factor3_value.set_markup("<span foreground='#FF9800'>No pool data</span>")
            self.prob_factor3_impact.set_markup("<span size='small' foreground='#CCCCCC'>+0.00%</span>")
        
        # Factor 4: Search Speed
        speed_mks = 0
        if hasattr(self, 'speed_value'):
            speed_text = self.speed_value.get_text()
            try:
                speed_mks = float(speed_text.replace('Mk/s', '').strip())
            except:
                pass
        
        if speed_mks > 200:
            factor4_score = 15
            color = '#4CAF50'
        elif speed_mks > 100:
            factor4_score = 10
            color = '#8BC34A'
        elif speed_mks > 50:
            factor4_score = 5
            color = '#FF9800'
        else:
            factor4_score = 0
            color = '#CCCCCC'
        
        self.prob_factor4_value.set_markup(
            f"<span foreground='{color}'>{speed_mks:.2f} Mk/s</span>"
        )
        self.prob_factor4_impact.set_markup(
            f"<span size='small' foreground='{color}'>+{factor4_score:.2f}%</span>"
        )
        
        # Factor 5: Time Investment
        runtime_seconds = 0
        if self.start_time:
            runtime_seconds = (datetime.now() - self.start_time).total_seconds()
        
        hours = runtime_seconds / 3600
        if hours > 100:
            factor5_score = 10
        elif hours > 24:
            factor5_score = 8
        elif hours > 10:
            factor5_score = 6
        elif hours > 1:
            factor5_score = 3
        else:
            factor5_score = 1
        
        time_str = str(timedelta(seconds=int(runtime_seconds)))
        self.prob_factor5_value.set_markup(
            f"<span foreground='#4CAF50'>{time_str}</span>"
        )
        self.prob_factor5_impact.set_markup(
            f"<span size='small' foreground='#4CAF50'>+{factor5_score:.2f}%</span>"
        )
        
        # Calculate total probability
        total_prob = self.calculate_discovery_probability()
        
        # Update main probability label
        if total_prob < 10:
            color = '#F44336'
            status = "Very Low"
        elif total_prob < 30:
            color = '#FF9800'
            status = "Low"
        elif total_prob < 60:
            color = '#FFEB3B'
            status = "Medium"
        else:
            color = '#4CAF50'
            status = "High"
        
        self.probability_label.set_markup(
            f"<span size='large' weight='bold'>Current Discovery Probability: "
            f"<span foreground='{color}'>{total_prob:.2f}% ({status})</span></span>"
        )
        
        # Generate recommendations
        recommendations = []
        
        if not pattern_active:
            recommendations.append("⚡ Enable pattern filters to increase efficiency by 2-10x")
        
        if pool_count == 0:
            recommendations.append("🔄 Click 'Scrape Pool Now' to avoid duplicate work")
        
        if speed_mks < 50:
            recommendations.append("🚀 GPU speed is low - check CUDA configuration or GPU selection")
        
        if coverage_percent < 1:
            recommendations.append("⏰ Let it run longer to increase coverage")
        
        if hours < 1:
            recommendations.append("⏱ Search has just started - probability increases with time")
        
        if len(pattern_active) < 3:
            recommendations.append("🎯 Enable all three pattern filters for maximum optimization")
        
        if pool_coverage < 30:
            recommendations.append("📡 Pool has low coverage - good opportunity for you!")
        
        if not recommendations:
            recommendations.append("✅ Excellent setup! Keep searching - you're doing great!")
        
        rec_text = "\n".join([f"• {rec}" for rec in recommendations[:5]])  # Top 5 recommendations
        self.prob_recommendations.set_markup(
            f"<span size='small'>{rec_text}</span>"
        )
        
        # Redraw probability bar
        if hasattr(self, 'probability_drawing'):
            self.probability_drawing.queue_draw()
    
    def update_pattern_reduction(self, widget=None):
        """Update estimated search space reduction based on selected patterns"""
        reduction = 0
        
        if self.exclude_iter3.get_active():
            reduction += 60
        if self.exclude_iter4.get_active():
            reduction += 40
        if self.exclude_alphanum.get_active():
            reduction += 30
        
        # Cap at 95% (can't combine additively)
        reduction = min(reduction, 95)
        
        self.pattern_reduction_label.set_markup(
            f"<span foreground='#00FFFF' weight='bold'>"
            f"Estimated search space reduction: {reduction}%"
            f"</span>"
        )
    
    def has_repeated_chars(self, hex_string, min_repeats=3):
        """Check if hex string has N or more repeated characters (ignoring zeros)"""
        count = 1
        prev_char = ''
        
        for char in hex_string:
            if char == prev_char:
                count += 1
                # IGNORE repeated zeros - they're common in valid ranges
                if count >= min_repeats and char != '0':
                    return True
            else:
                count = 1
                prev_char = char
        
        return False
    
    def is_all_alpha_or_numeric(self, hex_string):
        """Check if hex string is entirely letters (A-F) or numbers (0-9)"""
        has_alpha = any(c in 'ABCDEFabcdef' for c in hex_string)
        has_numeric = any(c in '0123456789' for c in hex_string)
        
        # If it has both, return False (mixed is good)
        # If it has only one type, return True (should exclude)
        return has_alpha ^ has_numeric  # XOR: true if only one is true
    
    def should_skip_block_by_pattern(self, block_start, block_end):
        """Check if block should be skipped based on pattern exclusions"""
        # Convert to hex strings
        start_hex = hex(block_start)[2:].upper()
        end_hex = hex(block_end)[2:].upper()
        
        # Check exclude_iter3
        if self.exclude_iter3.get_active():
            if self.has_repeated_chars(start_hex, 3) or self.has_repeated_chars(end_hex, 3):
                return True, "repeated-3"
        
        # Check exclude_iter4
        if self.exclude_iter4.get_active():
            if self.has_repeated_chars(start_hex, 4) or self.has_repeated_chars(end_hex, 4):
                return True, "repeated-4"
        
        # Check exclude_alphanum
        if self.exclude_alphanum.get_active():
            if self.is_all_alpha_or_numeric(start_hex) or self.is_all_alpha_or_numeric(end_hex):
                return True, "alphanum-only"
        
        return False, None
    
    def on_load_preset(self, button):
        """Load preset values for selected puzzle"""
        if self.is_running:
            dialog = Gtk.MessageDialog(
                transient_for=self,
                flags=0,
                message_type=Gtk.MessageType.WARNING,
                buttons=Gtk.ButtonsType.OK,
                text="Cannot switch puzzle while running!"
            )
            dialog.format_secondary_text("Please stop the search before switching puzzles.")
            dialog.run()
            dialog.destroy()
            return
        
        text = self.puzzle_combo.get_active_text()
        if not text:
            return
        
        puzzle_num = int(text.split('#')[1].split(' ')[0])
        preset = self.PUZZLE_PRESETS[puzzle_num]
        
        # Confirm switch
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Switch to {preset['name']}?"
        )
        dialog.format_secondary_text(
            f"This will:\n"
            f"• Load new database: scan_data_puzzle_{puzzle_num}.db\n"
            f"• Load new state file: keyhunt_state_puzzle_{puzzle_num}.json\n"
            f"• Update address to: {preset['address']}\n"
            f"• Update range: {preset['range_start']} to {preset['range_end']}\n\n"
            f"Your current puzzle data will be preserved."
        )
        
        response = dialog.run()
        dialog.destroy()
        
        if response == Gtk.ResponseType.YES:
            self.switch_to_puzzle(puzzle_num)
    
    def switch_to_puzzle(self, puzzle_num):
        """Switch to a different puzzle"""
        self.log(f"🔄 Switching to Puzzle #{puzzle_num}...", "info")
        
        # Save current state if needed
        if self.current_puzzle != puzzle_num:
            self.save_current_state()
        
        # Update puzzle number
        old_puzzle = self.current_puzzle
        self.current_puzzle = puzzle_num
        
        # Switch components to new puzzle
        self.pool_scraper.update_puzzle(puzzle_num)
        self.scan_db.switch_puzzle(puzzle_num)
        self.state_mgr.switch_puzzle(puzzle_num)
        
        # Load preset values
        preset = self.PUZZLE_PRESETS[puzzle_num]
        self.target_entry.set_text(preset['address'])
        self.range_start.set_text(preset['range_start'])
        self.range_end.set_text(preset['range_end'])
        
        # Reset state
        self.block_mgr = None
        self.current_block = None
        self.current_block_index = 0
        self.keys_checked = 0
        
        # Load previous state for this puzzle if exists
        state = self.state_mgr.load_state()
        if state and state.get('puzzle_number') == puzzle_num:
            self.log(f"📁 Found previous session for Puzzle #{puzzle_num}", "info")
            self.current_block_index = state.get('current_block_index', 0)
            self.keys_checked = state.get('keys_checked', 0)
            
            # Restore range if saved
            if 'range_start' in state:
                self.range_start.set_text(state['range_start'])
            if 'range_end' in state:
                self.range_end.set_text(state['range_end'])
        
        # Update UI
        self.puzzle_info_label.set_markup(
            f"<span size='small'>Current: {preset['name']} - {preset['bits']} bits - Reward: {preset['reward']}</span>"
        )
        self.db_info_label.set_markup(
            f"<span size='small' foreground='#CCCCCC'>Database: scan_data_puzzle_{puzzle_num}.db</span>"
        )
        
        # Update title
        self.set_title(f"KeyHunt Smart Coordinator v{__version__} - Puzzle #{puzzle_num}")
        
        # Update stats
        self.update_smart_status()
        
        # Refresh visual progress bar
        if self.progress_drawing:
            self.progress_drawing.queue_draw()
        
        self.log(f"✅ Switched to Puzzle #{puzzle_num} successfully!", "success")
        self.log(f"   Address: {preset['address']}", "info")
        self.log(f"   Range: {preset['range_start']} to {preset['range_end']}", "info")
        self.log(f"   Database: scan_data_puzzle_{puzzle_num}.db", "info")
        
        # Suggest initial scrape
        self.log(f"💡 Tip: Click 'Scrape Pool Now' to load exclusions for Puzzle #{puzzle_num}", "warning")
    
    def parse_manual_ranges(self, text):
        """Parse manual range input and return list of (start, end) tuples"""
        ranges = []
        lines = text.strip().split('\n')
        
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            try:
                # Try different separators
                if ':' in line:
                    parts = line.split(':')
                elif '-' in line:
                    parts = line.split('-')
                elif ' ' in line:
                    parts = line.split()
                else:
                    self.log(f"⚠ Line {line_num}: Invalid format (no separator): {line}", "warning")
                    continue
                
                if len(parts) != 2:
                    self.log(f"⚠ Line {line_num}: Expected 2 parts, got {len(parts)}: {line}", "warning")
                    continue
                
                # Parse hex values
                start = int(parts[0].strip(), 16)
                end = int(parts[1].strip(), 16)
                
                # Validate
                if start > end:
                    self.log(f"⚠ Line {line_num}: Start > End: {line}", "warning")
                    continue
                
                ranges.append((start, end))
                
            except ValueError as e:
                self.log(f"⚠ Line {line_num}: Invalid hex: {line} - {e}", "warning")
                continue
        
        return ranges
    
    def on_add_manual_pool_ranges(self, button):
        """Add manually entered ranges as pool-scanned"""
        buffer = self.manual_input_view.get_buffer()
        text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)
        
        if not text.strip():
            self.manual_status_label.set_markup("<span foreground='#FF9800'>⚠ No ranges entered</span>")
            return
        
        ranges = self.parse_manual_ranges(text)
        
        if not ranges:
            self.manual_status_label.set_markup("<span foreground='#F44336'>❌ No valid ranges found</span>")
            return
        
        # Add to database as pool scanned
        added_count, duplicate_count = self.scan_db.add_pool_blocks(ranges)
        self.cache_dirty = True  # Refresh cache
        
        # Update UI
        self.update_smart_status()
        if self.progress_drawing:
            self.progress_drawing.queue_draw()
        
        self.log(f"✅ Manual add: {added_count} new, {duplicate_count} duplicates", "success")
        self.manual_status_label.set_markup(
            f"<span foreground='#4CAF50'>✅ Added {added_count} new ({duplicate_count} duplicates)</span>"
        )
    
    def on_add_manual_my_ranges(self, button):
        """Add manually entered ranges as my-scanned"""
        buffer = self.manual_input_view.get_buffer()
        text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)
        
        if not text.strip():
            self.manual_status_label.set_markup("<span foreground='#FF9800'>⚠ No ranges entered</span>")
            return
        
        ranges = self.parse_manual_ranges(text)
        
        if not ranges:
            self.manual_status_label.set_markup("<span foreground='#F44336'>❌ No valid ranges found</span>")
            return
        
        # Add to database as my scanned (with 0 keys checked since manual)
        for start, end in ranges:
            self.scan_db.add_my_block(start, end, 0)
        self.cache_dirty = True  # Refresh cache
        
        # Update UI
        self.update_smart_status()
        if self.progress_drawing:
            self.progress_drawing.queue_draw()
        
        self.log(f"✅ Added {len(ranges)} ranges as my-scanned (manual)", "success")
        self.manual_status_label.set_markup(
            f"<span foreground='#4CAF50'>✅ Added {len(ranges)} ranges as my-scanned</span>"
        )
    
    def on_import_ranges_file(self, button):
        """Import ranges from a file"""
        dialog = Gtk.FileChooserDialog(
            title="Select Ranges File",
            parent=self,
            action=Gtk.FileChooserAction.OPEN
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN, Gtk.ResponseType.OK
        )
        
        # Add file filters
        filter_text = Gtk.FileFilter()
        filter_text.set_name("Text files")
        filter_text.add_mime_type("text/plain")
        filter_text.add_pattern("*.txt")
        dialog.add_filter(filter_text)
        
        filter_any = Gtk.FileFilter()
        filter_any.set_name("All files")
        filter_any.add_pattern("*")
        dialog.add_filter(filter_any)
        
        response = dialog.run()
        
        if response == Gtk.ResponseType.OK:
            filepath = dialog.get_filename()
            dialog.destroy()
            
            try:
                with open(filepath, 'r') as f:
                    content = f.read()
                
                # Set content in text view
                buffer = self.manual_input_view.get_buffer()
                buffer.set_text(content)
                
                # Parse to show preview
                ranges = self.parse_manual_ranges(content)
                
                self.log(f"📁 Imported file: {filepath}", "info")
                self.log(f"   Found {len(ranges)} valid ranges", "info")
                self.manual_status_label.set_markup(
                    f"<span foreground='#4CAF50'>✅ Loaded {len(ranges)} ranges from file</span>"
                )
                
            except Exception as e:
                self.log(f"❌ Error importing file: {e}", "error")
                self.manual_status_label.set_markup(
                    f"<span foreground='#F44336'>❌ Error: {e}</span>"
                )
        else:
            dialog.destroy()
    
    def on_clear_manual_input(self, button):
        """Clear manual input text"""
        buffer = self.manual_input_view.get_buffer()
        buffer.set_text("")
        self.manual_status_label.set_markup("<span foreground='#CCCCCC'>Input cleared</span>")
    
    def on_keyhunt_browse(self, button):
        """Browse for KeyHunt binary"""
        dialog = Gtk.FileChooserDialog(
            title="Select KeyHunt-Cuda",
            parent=self,
            action=Gtk.FileChooserAction.OPEN
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN, Gtk.ResponseType.OK
        )
        
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self.keyhunt_path.set_text(dialog.get_filename())
        dialog.destroy()


def main():
    app = KeyHuntSmartGUI()
    app.connect("destroy", Gtk.main_quit)
    app.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
