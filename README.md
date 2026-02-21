<div align="center">

# HexClaw
### AI-Powered Autonomous Cybersecurity Orchestration Platform

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Security](https://img.shields.io/badge/Security-Penetration%20Testing-red.svg)](https://github.com/0x4m4/hexclaw)
[![MCP](https://img.shields.io/badge/MCP-Compatible-purple.svg)](https://github.com/0x4m4/hexclaw)
[![Version](https://img.shields.io/badge/Version-1.0.0-orange.svg)](https://github.com/0x4m4/hexclaw/releases)
[![Tools](https://img.shields.io/badge/Security%20Tools-150%2B-brightgreen.svg)](https://github.com/0x4m4/hexclaw)
[![Agents](https://img.shields.io/badge/AI%20Agents-12%2B-purple.svg)](https://github.com/0x4m4/hexclaw)
[![Stars](https://img.shields.io/github/stars/0x4m4/hexclaw?style=social)](https://github.com/0x4m4/hexclaw)

**Advanced AI-powered autonomous cybersecurity orchestration platform with 150+ security tools, 12+ specialized AI agents, and MCP protocol integration**

[📋 Overview](#overview) • [🏗️ Architecture](#architecture) • [🚀 Installation](#installation) • [🛠️ Features](#features) • [🤖 AI Agents](#ai-agents) • [📖 Usage](#usage)

</div>

---

## Table of Contents

- [Overview](#overview)
- [What Makes HexClaw Different](#what-makes-hexclaw-different)
- [Architecture](#architecture)
- [Main Features](#main-features)
- [Use Cases](#use-cases)
- [Installation](#installation)
- [Usage](#usage)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Troubleshooting](#troubleshooting)
- [Security Considerations](#security-considerations)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

HexClaw is a cutting-edge autonomous cybersecurity orchestration platform that combines the power of AI with 150+ professional security tools. Built on the Model Context Protocol (MCP), HexClaw enables seamless integration with popular AI assistants including Claude Desktop, VS Code Copilot, Cursor, and Roo Code.

### Core Capabilities

**Dual-System Architecture:**
- **MCP Server** - Flask-based server exposing 150+ security tools via MCP protocol
- **HexClaw Daemon** - Asyncio-powered autonomous orchestrator for complex security workflows

**AI-Powered Intelligence:**
- 12+ specialized autonomous AI agents
- Intelligent decision engine for optimal tool selection
- Automatic parameter optimization
- Attack chain discovery and correlation
- Real-time adaptation based on results

**Comprehensive Security Arsenal:**
- 25+ Network reconnaissance and scanning tools
- 40+ Web application security testing tools
- 12+ Authentication and password security tools
- 25+ Binary analysis and reverse engineering tools
- 20+ Cloud and container security tools
- 20+ CTF and forensics tools
- 20+ Bug bounty and OSINT tools

**Advanced Orchestration:**
- YAML-based skill system for defining complex workflows
- Telegram bot interface for notifications and approvals
- Two-tier Redis caching with semantic matching
- Multi-database architecture (SQLite, DuckDB, PostgreSQL)
- Threat intelligence monitoring with automated alerts

---

## What Makes HexClaw Different

### 1. True Autonomous Orchestration

Unlike traditional penetration testing frameworks that require manual tool chaining, HexClaw features a sophisticated autonomous daemon that can:

- **Plan complex attack chains** using AI-powered goal decomposition
- **Execute multi-step workflows** with intelligent error recovery
- **Adapt in real-time** based on discovered vulnerabilities
- **Request operator approval** for sensitive operations via Telegram

### 2. MCP Protocol Integration

HexClaw is built from the ground up on the Model Context Protocol, enabling:

- **Seamless AI assistant integration** - Works with Claude, GPT, Copilot, and more
- **Standardized tool interfaces** - Consistent API across all 150+ tools
- **Context-aware execution** - AI agents understand tool capabilities and limitations
- **Extensible architecture** - Easy to add new tools and AI providers

### 3. Intelligent Caching System

HexClaw's two-tier caching dramatically reduces costs and improves performance:

- **Exact match cache** - Redis DB 0 for identical prompt/result pairs
- **Semantic cache** - Redis DB 1 with sentence-transformers embeddings
- **Numpy fallback** - Lightweight n-gram embeddings when Redis unavailable
- **Zero-token gating** - Cached responses consume no LLM tokens

### 4. Skill-Based Workflow System

Define complex security workflows in simple YAML:

```yaml
name: recon_osint
steps:
  - tool: amass
    output: subs
    notify: always
  - tool: rustscan
    input: subs
    output: ports
    gate: approve
```

### 5. Multi-Database Analytics

- **SQLite** - Job queue and token logging
- **DuckDB** - In-memory analytics on Parquet files
- **PostgreSQL** - Optional persistent storage
- **Redis** - High-performance caching

### 6. Real-Time Monitoring & Notifications

- **Telegram bot integration** - Get notified of job status, results, and alerts
- **Approval gates** - Require human approval for dangerous operations
- **Live dashboards** - Monitor active jobs and system performance
- **Threat intelligence** - Automated CVE monitoring and prioritization

### 7. Performance Optimizations

| Operation | Traditional Tools | HexClaw | Improvement |
|-----------|-------------------|---------|-------------|
| Subdomain Enumeration | 2-4 hours | 5-10 minutes | **24x faster** |
| Vulnerability Scanning | 4-8 hours | 15-30 minutes | **16x faster** |
| Web App Testing | 6-12 hours | 20-45 minutes | **18x faster** |
| CTF Challenge Solving | 1-6 hours | 2-15 minutes | **24x faster** |
| Report Generation | 4-12 hours | 2-5 minutes | **144x faster** |

---

## Architecture

```mermaid
%%{init: {"themeVariables": {
  "primaryColor": "#b71c1c",
  "secondaryColor": "#ff5252",
  "tertiaryColor": "#ff8a80",
  "background": "#2d0000",
  "edgeLabelBackground":"#b71c1c",
  "fontFamily": "monospace",
  "fontSize": "16px",
  "fontColor": "#fffde7",
  "nodeTextColor": "#fffde7"
}}}%%
graph TD
    A[AI Assistant - Claude/GPT/Copilot] -->|MCP Protocol| B[HexClaw MCP Server]
    
    B --> C[Intelligent Decision Engine]
    B --> D[HexClaw Daemon]
    B --> E[150+ Security Tools]
    
    D --> F[Skill Orchestrator]
    D --> G[Telegram Bot Interface]
    D --> H[Threat Intelligence Monitor]
    
    F --> I[recon_osint]
    F --> J[agent_plan]
    F --> K[dev_ops]
    F --> L[osint_mapping]
    
    G --> M[Notifications]
    G --> N[Approval Gates]
    G --> O[Status Updates]
    
    C --> P[Tool Selection AI]
    C --> Q[Parameter Optimization]
    C --> R[Attack Chain Discovery]
    
    E --> S[Network Tools]
    E --> T[Web App Tools]
    E --> U[Binary Tools]
    E --> V[Cloud Tools]
    
    D --> W[Cache System]
    W --> X[Redis Exact Match]
    W --> Y[Redis Semantic]
    W --> Z[Numpy Fallback]
    
    D --> AA[Database Layer]
    AA --> AB[SQLite Jobs]
    AA --> AC[DuckDB Analytics]
    AA --> AD[PostgreSQL Optional]
    
    style A fill:#b71c1c,stroke:#ff5252,stroke-width:3px,color:#fffde7
    style B fill:#ff5252,stroke:#b71c1c,stroke-width:4px,color:#fffde7
    style D fill:#ff8a80,stroke:#b71c1c,stroke-width:3px,color:#fffde7
    style C fill:#ff8a80,stroke:#b71c1c,stroke-width:2px,color:#fffde7
```

### System Components

**MCP Server (`hexstrike_server.py`)**
- Flask-based HTTP server exposing security tools
- 150+ tool endpoints with standardized interfaces
- Health check and telemetry endpoints
- Process management and monitoring

**HexClaw Daemon (`daemon.py`)**
- Asyncio-powered autonomous orchestrator
- Skill execution engine with YAML workflows
- Job queue management with SQLite
- Telegram integration for notifications and approvals

**Cache System (`cache.py`)**
- Two-tier Redis caching (exact + semantic)
- Numpy fallback for environments without Redis
- Automatic cache warming and eviction

**Inference Engine (`inference.py`)**
- Multi-provider LLM support (Google, OpenRouter, ZhipuAI)
- Complexity-based provider selection
- Token usage tracking and logging

**Monitor (`monitor.py`)**
- Continuous threat intelligence monitoring
- CVE prioritization and alerting
- Shodan integration for asset discovery

**Planner (`planner.py`)**
- AI-powered goal decomposition
- Natural language to skill translation
- Context-aware workflow selection

---

## Main Features

### Security Tools Arsenal

#### 🔍 Network Reconnaissance & Scanning (25+ Tools)

- **Nmap** - Advanced port scanning with custom NSE scripts and service detection
- **Rustscan** - Ultra-fast port scanner with intelligent rate limiting
- **Masscan** - High-speed Internet-scale port scanning with banner grabbing
- **AutoRecon** - Comprehensive automated reconnaissance with 35+ parameters
- **Amass** - Advanced subdomain enumeration and OSINT gathering
- **Subfinder** - Fast passive subdomain discovery with multiple sources
- **Fierce** - DNS reconnaissance and zone transfer testing
- **DNSEnum** - DNS information gathering and subdomain brute forcing
- **TheHarvester** - Email and subdomain harvesting from multiple sources
- **ARP-Scan** - Network discovery using ARP requests
- **NBTScan** - NetBIOS name scanning and enumeration
- **RPCClient** - RPC enumeration and null session testing
- **Enum4linux** - SMB enumeration with user, group, and share discovery
- **Enum4linux-ng** - Advanced SMB enumeration with enhanced logging
- **SMBMap** - SMB share enumeration and exploitation
- **Responder** - LLMNR, NBT-NS and MDNS poisoner for credential harvesting
- **NetExec** - Network service exploitation framework (formerly CrackMapExec)

#### 🌐 Web Application Security Testing (40+ Tools)

- **Gobuster** - Directory, file, and DNS enumeration with intelligent wordlists
- **Dirsearch** - Advanced directory and file discovery with enhanced logging
- **Feroxbuster** - Recursive content discovery with intelligent filtering
- **FFuf** - Fast web fuzzer with advanced filtering and parameter discovery
- **Dirb** - Comprehensive web content scanner with recursive scanning
- **HTTPx** - Fast HTTP probing and technology detection
- **Katana** - Next-generation crawling and spidering with JavaScript support
- **Hakrawler** - Fast web endpoint discovery and crawling
- **Gau** - Get All URLs from multiple sources (Wayback, Common Crawl, etc.)
- **Waybackurls** - Historical URL discovery from Wayback Machine
- **Nuclei** - Fast vulnerability scanner with 4000+ templates
- **Nikto** - Web server vulnerability scanner with comprehensive checks
- **SQLMap** - Advanced automatic SQL injection testing with tamper scripts
- **WPScan** - WordPress security scanner with vulnerability database
- **Arjun** - HTTP parameter discovery with intelligent fuzzing
- **ParamSpider** - Parameter mining from web archives
- **X8** - Hidden parameter discovery with advanced techniques
- **Jaeles** - Advanced vulnerability scanning with custom signatures
- **Dalfox** - Advanced XSS vulnerability scanning with DOM analysis
- **Wafw00f** - Web application firewall fingerprinting
- **TestSSL** - SSL/TLS configuration testing and vulnerability assessment
- **SSLScan** - SSL/TLS cipher suite enumeration
- **SSLyze** - Fast and comprehensive SSL/TLS configuration analyzer
- **JWT-Tool** - JSON Web Token testing with algorithm confusion
- **GraphQL-Voyager** - GraphQL schema exploration and introspection testing
- **Burp Suite Extensions** - Custom extensions for advanced web testing
- **ZAP Proxy** - OWASP ZAP integration for automated security scanning
- **Wfuzz** - Web application fuzzer with advanced payload generation
- **Commix** - Command injection exploitation tool with automated detection
- **NoSQLMap** - NoSQL injection testing for MongoDB, CouchDB, etc.
- **Tplmap** - Server-side template injection exploitation tool

#### 🌐 Advanced Browser Agent

- **Headless Chrome Automation** - Full Chrome browser automation with Selenium
- **Screenshot Capture** - Automated screenshot generation for visual inspection
- **DOM Analysis** - Deep DOM tree analysis and JavaScript execution monitoring
- **Network Traffic Monitoring** - Real-time network request/response logging
- **Security Header Analysis** - Comprehensive security header validation
- **Form Detection & Analysis** - Automatic form discovery and input field analysis
- **JavaScript Execution** - Dynamic content analysis with full JavaScript support
- **Proxy Integration** - Seamless integration with Burp Suite and other proxies
- **Multi-page Crawling** - Intelligent web application spidering and mapping
- **Performance Metrics** - Page load times, resource usage, and optimization insights

#### 🔐 Authentication & Password Security (12+ Tools)

- **Hydra** - Network login cracker supporting 50+ protocols
- **John the Ripper** - Advanced password hash cracking with custom rules
- **Hashcat** - World's fastest password recovery tool with GPU acceleration
- **Medusa** - Speedy, parallel, modular login brute-forcer
- **Patator** - Multi-purpose brute-forcer with advanced modules
- **NetExec** - Swiss army knife for pentesting networks
- **SMBMap** - SMB share enumeration and exploitation tool
- **Evil-WinRM** - Windows Remote Management shell with PowerShell integration
- **Hash-Identifier** - Hash type identification tool
- **HashID** - Advanced hash algorithm identifier with confidence scoring
- **CrackStation** - Online hash lookup integration
- **Ophcrack** - Windows password cracker using rainbow tables

#### 🔬 Binary Analysis & Reverse Engineering (25+ Tools)

- **GDB** - GNU Debugger with Python scripting and exploit development support
- **GDB-PEDA** - Python Exploit Development Assistance for GDB
- **GDB-GEF** - GDB Enhanced Features for exploit development
- **Radare2** - Advanced reverse engineering framework with comprehensive analysis
- **Ghidra** - NSA's software reverse engineering suite with headless analysis
- **IDA Free** - Interactive disassembler with advanced analysis capabilities
- **Binary Ninja** - Commercial reverse engineering platform
- **Binwalk** - Firmware analysis and extraction tool with recursive extraction
- **ROPgadget** - ROP/JOP gadget finder with advanced search capabilities
- **Ropper** - ROP gadget finder and exploit development tool
- **One-Gadget** - Find one-shot RCE gadgets in libc
- **Checksec** - Binary security property checker with comprehensive analysis
- **Strings** - Extract printable strings from binaries with filtering
- **Objdump** - Display object file information with Intel syntax
- **Readelf** - ELF file analyzer with detailed header information
- **XXD** - Hex dump utility with advanced formatting
- **Hexdump** - Hex viewer and editor with customizable output
- **Pwntools** - CTF framework and exploit development library
- **Angr** - Binary analysis platform with symbolic execution
- **Libc-Database** - Libc identification and offset lookup tool
- **Pwninit** - Automate binary exploitation setup
- **Volatility** - Advanced memory forensics framework
- **MSFVenom** - Metasploit payload generator with advanced encoding
- **UPX** - Executable packer/unpacker for binary analysis

#### ☁️ Cloud & Container Security (20+ Tools)

- **Prowler** - AWS/Azure/GCP security assessment with compliance checks
- **Scout Suite** - Multi-cloud security auditing for AWS, Azure, GCP, Alibaba Cloud
- **CloudMapper** - AWS network visualization and security analysis
- **Pacu** - AWS exploitation framework with comprehensive modules
- **Trivy** - Comprehensive vulnerability scanner for containers and IaC
- **Clair** - Container vulnerability analysis with detailed CVE reporting
- **Kube-Hunter** - Kubernetes penetration testing with active/passive modes
- **Kube-Bench** - CIS Kubernetes benchmark checker with remediation
- **Docker Bench Security** - Docker security assessment following CIS benchmarks
- **Falco** - Runtime security monitoring for containers and Kubernetes
- **Checkov** - Infrastructure as code security scanning
- **Terrascan** - Infrastructure security scanner with policy-as-code
- **CloudSploit** - Cloud security scanning and monitoring
- **AWS CLI** - Amazon Web Services command line with security operations
- **Azure CLI** - Microsoft Azure command line with security assessment
- **GCloud** - Google Cloud Platform command line with security tools
- **Kubectl** - Kubernetes command line with security context analysis
- **Helm** - Kubernetes package manager with security scanning
- **Istio** - Service mesh security analysis and configuration assessment
- **OPA** - Policy engine for cloud-native security and compliance

#### 🏆 CTF & Forensics Tools (20+ Tools)

- **Volatility** - Advanced memory forensics framework with comprehensive plugins
- **Volatility3** - Next-generation memory forensics with enhanced analysis
- **Foremost** - File carving and data recovery with signature-based detection
- **PhotoRec** - File recovery software with advanced carving capabilities
- **TestDisk** - Disk partition recovery and repair tool
- **Steghide** - Steganography detection and extraction with password support
- **Stegsolve** - Steganography analysis tool with visual inspection
- **Zsteg** - PNG/BMP steganography detection tool
- **Outguess** - Universal steganographic tool for JPEG images
- **ExifTool** - Metadata reader/writer for various file formats
- **Binwalk** - Firmware analysis and reverse engineering with extraction
- **Scalpel** - File carving tool with configurable headers and footers
- **Bulk Extractor** - Digital forensics tool for extracting features
- **Autopsy** - Digital forensics platform with timeline analysis
- **Sleuth Kit** - Collection of command-line digital forensics tools

**Cryptography & Hash Analysis:**
- **John the Ripper** - Password cracker with custom rules and advanced modes
- **Hashcat** - GPU-accelerated password recovery with 300+ hash types
- **Hash-Identifier** - Hash type identification with confidence scoring
- **CyberChef** - Web-based analysis toolkit for encoding and encryption
- **Cipher-Identifier** - Automatic cipher type detection and analysis
- **Frequency-Analysis** - Statistical cryptanalysis for substitution ciphers
- **RSATool** - RSA key analysis and common attack implementations
- **FactorDB** - Integer factorization database for cryptographic challenges

#### 🔥 Bug Bounty & OSINT Arsenal (20+ Tools)

- **Amass** - Advanced subdomain enumeration and OSINT gathering
- **Subfinder** - Fast passive subdomain discovery with API integration
- **Hakrawler** - Fast web endpoint discovery and crawling
- **HTTPx** - Fast and multi-purpose HTTP toolkit with technology detection
- **ParamSpider** - Mining parameters from web archives
- **Aquatone** - Visual inspection of websites across hosts
- **Subjack** - Subdomain takeover vulnerability checker
- **DNSEnum** - DNS enumeration script with zone transfer capabilities
- **Fierce** - Domain scanner for locating targets with DNS analysis
- **TheHarvester** - Email and subdomain harvesting from multiple sources
- **Sherlock** - Username investigation across 400+ social networks
- **Social-Analyzer** - Social media analysis and OSINT gathering
- **Recon-ng** - Web reconnaissance framework with modular architecture
- **Maltego** - Link analysis and data mining for OSINT investigations
- **SpiderFoot** - OSINT automation with 200+ modules
- **Shodan** - Internet-connected device search with advanced filtering
- **Censys** - Internet asset discovery with certificate analysis
- **Have I Been Pwned** - Breach data analysis and credential exposure
- **Pipl** - People search engine integration for identity investigation
- **TruffleHog** - Git repository secret scanning with entropy analysis

### AI Agents

**12+ Specialized Autonomous AI Agents:**

- **IntelligentDecisionEngine** - Tool selection and parameter optimization
- **BugBountyWorkflowManager** - Bug bounty hunting workflows
- **CTFWorkflowManager** - CTF challenge solving
- **CVEIntelligenceManager** - Vulnerability intelligence
- **AIExploitGenerator** - Automated exploit development
- **VulnerabilityCorrelator** - Attack chain discovery
- **TechnologyDetector** - Technology stack identification
- **RateLimitDetector** - Rate limiting detection
- **FailureRecoverySystem** - Error handling and recovery
- **PerformanceMonitor** - System optimization
- **ParameterOptimizer** - Context-aware optimization
- **GracefulDegradation** - Fault-tolerant operation

### Advanced Features

- **Smart Caching System** - Two-tier Redis cache with semantic matching and numpy fallback
- **Real-time Process Management** - Live command control and monitoring
- **Vulnerability Intelligence** - CVE monitoring and exploit analysis
- **Browser Agent** - Headless Chrome automation for web testing
- **API Security Testing** - GraphQL, JWT, REST API security assessment
- **Modern Visual Engine** - Real-time dashboards and progress tracking
- **Telegram Bot Interface** - Notifications, approvals, and status updates
- **Skill-Based Workflows** - YAML-defined complex security workflows
- **Multi-Database Analytics** - SQLite, DuckDB, and PostgreSQL support
- **Threat Intelligence Monitor** - Automated CVE monitoring and prioritization

---

## Use Cases

### 1. Penetration Testing

HexClaw automates the entire penetration testing lifecycle:

**Reconnaissance Phase:**
- Automated subdomain enumeration with Amass and Subfinder
- Port scanning with Rustscan and Nmap
- Service fingerprinting and technology detection
- OSINT gathering for target organization

**Scanning Phase:**
- Web application vulnerability scanning with Nuclei
- SQL injection testing with SQLMap
- Directory brute forcing with Gobuster and FFuf
- SSL/TLS configuration analysis

**Exploitation Phase:**
- Automated exploit generation with AI assistance
- Privilege escalation pathway discovery
- Lateral movement opportunity identification
- Attack chain correlation and optimization

**Reporting Phase:**
- Automated report generation with vulnerability cards
- Risk scoring and prioritization
- Remediation recommendations
- Executive summary generation

### 2. Bug Bounty Hunting

HexClaw excels at bug bounty programs:

- **Target Discovery** - Automated subdomain and asset discovery
- **Vulnerability Hunting** - Multi-tool scanning with intelligent deduplication
- **Impact Analysis** - Automated severity scoring and business impact assessment
- **Report Drafting** - AI-generated vulnerability reports with proof of concept
- **Workflow Optimization** - Skill-based workflows for common bug types (XSS, SQLi, IDOR, etc.)

### 3. CTF Competitions

HexClaw provides a competitive edge in CTF challenges:

- **Binary Exploitation** - Automated binary analysis with Angr and Pwntools
- **Cryptography** - Automated cipher identification and analysis
- **Forensics** - File carving, steganography detection, and memory analysis
- **Web Challenges** - Automated web application exploitation
- **OSINT** - Information gathering and correlation

### 4. Red Team Operations

HexClaw supports sophisticated red team engagements:

- **Initial Access** - Automated phishing and external attack surface analysis
- **Execution** - Automated command and control setup
- **Persistence** - Automated persistence mechanism discovery
- **Privilege Escalation** - Automated privilege escalation pathway identification
- **Defense Evasion** - Automated technique selection and optimization
- **Lateral Movement** - Automated network traversal and credential harvesting
- **Exfiltration** - Automated data exfiltration pathway discovery

### 5. Security Research

HexClaw aids security researchers:

- **Vulnerability Research** - Automated vulnerability discovery and analysis
- **Exploit Development** - AI-assisted exploit generation
- **Malware Analysis** - Automated binary and behavior analysis
- **Threat Intelligence** - Automated threat gathering and correlation
- **Zero-Day Hunting** - Automated vulnerability pattern discovery

### 6. Compliance & Auditing

HexClaw supports security compliance:

- **CIS Benchmarks** - Automated CIS benchmark scanning with Kube-Bench and Docker Bench
- **Cloud Security** - Multi-cloud security assessment with Prowler and Scout Suite
- **Container Security** - Container vulnerability scanning with Trivy
- **Infrastructure as Code** - IaC security scanning with Checkov and Terrascan

### 7. DevSecOps Integration

HexClaw integrates into DevSecOps pipelines:

- **CI/CD Integration** - Automated security testing in CI/CD pipelines
- **Infrastructure Scanning** - Automated infrastructure security assessment
- **Container Scanning** - Automated container vulnerability scanning
- **Secret Detection** - Automated secret detection with TruffleHog
- **Policy Enforcement** - OPA-based policy enforcement

---

## Installation

### Prerequisites

- **Python 3.8+** - Required for all components
- **Redis Server** - Recommended for caching (optional but recommended)
- **PostgreSQL** - Optional for persistent storage
- **Kali Linux 2024+** - Recommended for security tool availability
- **Chrome/Chromium** - Required for browser agent
- **Telegram Bot Token** - Required for daemon notifications

### Quick Setup

#### 1. Clone the Repository

```bash
git clone https://github.com/0x4m4/hexclaw.git
cd hexclaw
```

#### 2. Create Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows
```

#### 3. Install Python Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

#### 4. Install Security Tools

**Core Tools (Essential):**
```bash
# Network & Reconnaissance
nmap masscan rustscan amass subfinder nuclei fierce dnsenum
autorecon theharvester responder netexec enum4linux-ng

# Web Application Security
gobuster feroxbuster dirsearch ffuf dirb httpx katana
nikto sqlmap wpscan arjun paramspider dalfox wafw00f

# Password & Authentication
hydra john hashcat medusa patator crackmapexec
evil-winrm hash-identifier ophcrack

# Binary Analysis & Reverse Engineering
gdb radare2 binwalk ghidra checksec strings objdump
volatility3 foremost steghide exiftool
```

**Cloud Security Tools:**
```bash
prowler scout-suite trivy
kube-hunter kube-bench docker-bench-security
```

**Browser Agent Requirements:**
```bash
# Chrome/Chromium for Browser Agent
sudo apt install chromium-browser chromium-chromedriver
# OR install Google Chrome
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list
sudo apt update && sudo apt install google-chrome-stable
```

**Kali Linux Users:**
```bash
# Install Kali meta-packages for most tools
sudo apt install -y kali-tools-top10
sudo apt install -y amass subfinder httpx-toolkit nuclei masscan ffuf rustscan
```

#### 5. Install System Dependencies

```bash
# Python + build tools
sudo apt install -y python3 python3-pip python3-venv git curl

# Redis (inference cache)
sudo apt install -y redis-server
sudo systemctl enable redis-server --now

# PostgreSQL (optional — data.py analytics)
sudo apt install -y postgresql postgresql-client
sudo systemctl enable postgresql --now
```

#### 6. Configure Environment Variables

Create `.env` in the project root:

```bash
cat > .env << 'EOF'
# ── Telegram (REQUIRED) ──────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN=<your-bot-token>
TELEGRAM_CHAT_ID=<your-chat-id>

# ── AI Provider Keys ─────────────────────────────────────────────────────────
GOOGLE_API_KEY=<gemini-api-key>
# OPENROUTER_API_KEY=<optional>
# ZHIPUAI_API_KEY=<optional>

# ── Infrastructure ───────────────────────────────────────────────────────────
REDIS_URL=redis://localhost:6379/0
POSTGRES_DSN=postgresql://hexclaw:hexclaw@localhost:5432/hexclaw

# ── Monitor ──────────────────────────────────────────────────────────────────
# SHODAN_API_KEY=<optional>
# MONITOR_INTERVAL_SEC=900
# ALERT_MIN_SEVERITY=medium

# ── Email (optional) ─────────────────────────────────────────────────────────
# APP_EMAIL=<gmail-or-m365>
# APP_EMAIL_PASS=<app-password>
# M365_EMAIL=<m365-email>
# M365_PASS=<m365-password>

# ── Logging ──────────────────────────────────────────────────────────────────
# TG_LOG_LEVEL=INFO          # DEBUG, INFO, WARNING, ERROR
# TG_LOG_BATCH_SEC=3         # batch interval for log forwarding
EOF

chmod 600 .env
```

**Getting a Telegram Bot Token:**
1. Message **@BotFather** on Telegram
2. Send `/newbot` → follow prompts → copy the token
3. Add the bot to your group/DM it once
4. Get your chat ID:
   ```bash
   curl -s "https://api.telegram.org/bot<TOKEN>/getUpdates" | python3 -m json.tool | grep '"id"'
   ```

#### 7. Database Setup (Optional)

**PostgreSQL:**
```bash
sudo -u postgres psql -c "CREATE USER hexclaw WITH PASSWORD 'hexclaw';"
sudo -u postgres psql -c "CREATE DATABASE hexclaw OWNER hexclaw;"
```

**Redis:**
```bash
redis-cli ping   # → PONG
```

SQLite databases (`jobs.db`, `token_log.db`) are created automatically in `./data/`.

#### 8. Interactive Setup Wizard

Run the interactive setup wizard for guided installation:

```bash
python install.py
```

### Installation Verification

```bash
# Verify Python dependencies
python3 -c "import flask, fastmcp, selenium; print('Dependencies OK')"

# Verify key security tools
nmap --version
nuclei -version
amass -version
redis-cli ping          # → PONG

# Test MCP server health
curl http://localhost:8888/health
```

---

## Usage

### Starting the System

#### 1. Start the MCP Server

```bash
# Start the MCP server
python3 hexstrike_server.py

# Optional: Start with debug mode
python3 hexstrike_server.py --debug

# Optional: Custom port configuration
HEXSTRIKE_PORT=8888 python3 hexstrike_server.py
```

#### 2. Start the HexClaw Daemon

```bash
# Start the autonomous daemon
python3 daemon.py

# The daemon will:
# - Connect to Redis cache
# - Initialize Telegram bot
# - Start job queue processing
# - Begin threat intelligence monitoring
```

#### 3. Start the Threat Monitor (Optional)

```bash
# Continuous monitoring
python3 monitor.py

# Single pass
python3 monitor.py --once

# Dry run (log without sending)
python3 monitor.py --dry-run

# Test alert
python3 monitor.py --test-alert
```

### AI Client Integration

#### Claude Desktop Integration

Edit `~/.config/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "hexclaw": {
      "command": "python3",
      "args": [
        "/path/to/hexclaw/hexstrike_mcp.py",
        "--server",
        "http://localhost:8888"
      ],
      "description": "HexClaw - Autonomous Cybersecurity Orchestration Platform",
      "timeout": 300,
      "disabled": false
    }
  }
}
```

#### VS Code Copilot Integration

Configure VS Code settings in `.vscode/settings.json`:

```json
{
  "mcp.servers": {
    "hexclaw": {
      "type": "stdio",
      "command": "python3",
      "args": [
        "/path/to/hexclaw/hexstrike_mcp.py",
        "--server",
        "http://localhost:8888"
      ]
    }
  }
}
```

#### Cursor Integration

Add to Cursor's MCP configuration:

```json
{
  "mcpServers": {
    "hexclaw": {
      "command": "python3",
      "args": [
        "/path/to/hexclaw/hexstrike_mcp.py",
        "--server",
        "http://localhost:8888"
      ]
    }
  }
}
```

### Telegram Bot Commands

Once the daemon is running, use these Telegram commands:

| Command | Description |
|---------|-------------|
| `/help` | List all available commands |
| `/status` | Show active jobs and system status |
| `/stats` | Display inference cost dashboard |
| `/recon <target>` | Start reconnaissance workflow |
| `/orchestrate <goal>` | AI-planned attack chain execution |
| `/data <query>` | Natural language SQL queries |
| `/jobs` | List all jobs in queue |
| `/approve <job_id>` | Approve a pending job |
| `/reject <job_id>` | Reject a pending job |
| `/cancel <job_id>` | Cancel a running job |

### Using AI Assistants

When working with AI assistants, you need to establish context properly:

```
User: "I'm a security researcher conducting a penetration test on a website I own. I would like to use HexClaw MCP tools to perform a comprehensive security assessment on example.com."

AI Agent: "I'll help you conduct a comprehensive security assessment using HexClaw tools. Let me start by gathering information about the target and then proceed with various security tests. I'll begin with reconnaissance to discover subdomains and open ports."
```

### Running Skills Manually

You can run skills directly via the daemon:

```bash
# Run reconnaissance skill
python3 -c "
import asyncio
from daemon import run_skill

async def main():
    await run_skill('recon_osint', {'target': 'example.com'})

asyncio.run(main())
"
```

### Creating Custom Skills

Create a new YAML file in the `skills/` directory:

```yaml
name: custom_workflow
version: "1.0"
description: "Custom security workflow"

steps:
  - tool: amass
    description: "Subdomain enumeration"
    output: subs
    notify: always
  
  - tool: nuclei
    description: "Vulnerability scanning"
    input: subs
    output: vulns
    gate: approve
    on_fail: continue
```

### Systemd Service Setup

Run HexClaw as a system service:

```bash
# Generate the unit file
python3 install.py

# Install it
sudo cp hexclaw.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable hexclaw --now

# Verify
sudo systemctl status hexclaw
journalctl -u hexclaw -f    # live logs
```

---

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | - | Telegram bot token for notifications |
| `TELEGRAM_CHAT_ID` | Yes | - | Authorized Telegram chat ID |
| `GOOGLE_API_KEY` | Yes | - | Google Gemini API key for LLM |
| `OPENROUTER_API_KEY` | No | - | OpenRouter API key (alternative LLM) |
| `ZHIPUAI_API_KEY` | No | - | ZhipuAI API key (alternative LLM) |
| `REDIS_URL` | No | redis://localhost:6379/0 | Redis connection string |
| `POSTGRES_DSN` | No | - | PostgreSQL connection string |
| `SHODAN_API_KEY` | No | - | Shodan API key for threat intel |
| `MONITOR_INTERVAL_SEC` | No | 900 | Monitor polling interval |
| `ALERT_MIN_SEVERITY` | No | medium | Minimum severity for alerts |
| `TG_LOG_LEVEL` | No | INFO | Telegram log level |
| `TG_LOG_BATCH_SEC` | No | 3 | Log batch interval |
| `HEXSTRIKE_PORT` | No | 8888 | MCP server port |
| `HEXSTRIKE_HOST` | No | 127.0.0.1 | MCP server host |

### Skill Configuration

Skills are configured via YAML files in the `skills/` directory. Each skill file defines:

- **name** - Skill identifier
- **version** - Skill version
- **description** - Skill purpose
- **approval_required** - Whether entire skill requires approval
- **max_runtime_sec** - Maximum execution time
- **notify_on_start** - Whether to notify on skill start
- **steps** - List of workflow steps

Each step can have:
- **tool** - MCP tool name
- **description** - Step description
- **input** - Context key to read from
- **output** - Context key to write to
- **action** - Internal action type
- **params** - Additional parameters
- **on_fail** - Behavior on failure (continue/abort)
- **notify** - When to notify (always/on_error/never)
- **gate** - Approval requirement (none/approve)

---

## API Reference

### Core System Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Server health check with tool availability |
| `/api/command` | POST | Execute arbitrary commands with caching |
| `/api/telemetry` | GET | System performance metrics |
| `/api/cache/stats` | GET | Cache performance statistics |
| `/api/intelligence/analyze-target` | POST | AI-powered target analysis |
| `/api/intelligence/select-tools` | POST | Intelligent tool selection |
| `/api/intelligence/optimize-parameters` | POST | Parameter optimization |

### Common MCP Tools

**Network Security Tools:**
- `nmap_scan()` - Advanced Nmap scanning with optimization
- `rustscan_scan()` - Ultra-fast port scanning
- `masscan_scan()` - High-speed port scanning
- `autorecon_scan()` - Comprehensive reconnaissance
- `amass_enum()` - Subdomain enumeration and OSINT

**Web Application Tools:**
- `gobuster_scan()` - Directory and file enumeration
- `feroxbuster_scan()` - Recursive content discovery
- `ffuf_scan()` - Fast web fuzzing
- `nuclei_scan()` - Vulnerability scanning with templates
- `sqlmap_scan()` - SQL injection testing
- `wpscan_scan()` - WordPress security assessment

**Binary Analysis Tools:**
- `ghidra_analyze()` - Software reverse engineering
- `radare2_analyze()` - Advanced reverse engineering
- `gdb_debug()` - GNU debugger with exploit development
- `pwntools_exploit()` - CTF framework and exploit development
- `angr_analyze()` - Binary analysis with symbolic execution

**Cloud Security Tools:**
- `prowler_assess()` - AWS/Azure/GCP security assessment
- `scout_suite_audit()` - Multi-cloud security auditing
- `trivy_scan()` - Container vulnerability scanning
- `kube_hunter_scan()` - Kubernetes penetration testing
- `kube_bench_check()` - CIS Kubernetes benchmark assessment

### Process Management

| Action | Endpoint | Description |
|--------|----------|-------------|
| **List Processes** | `GET /api/processes/list` | List all active processes |
| **Process Status** | `GET /api/processes/status/<pid>` | Get detailed process information |
| **Terminate** | `POST /api/processes/terminate/<pid>` | Stop specific process |
| **Dashboard** | `GET /api/processes/dashboard` | Live monitoring dashboard |

---

## Troubleshooting

### Common Issues

#### 1. MCP Connection Failed

```bash
# Check if server is running
netstat -tlnp | grep 8888

# Restart server
python3 hexstrike_server.py

# Check server logs
tail -f logs/daemon.log
```

#### 2. Security Tools Not Found

```bash
# Check tool availability
which nmap gobuster nuclei

# Install missing tools from their official sources
# On Kali Linux:
sudo apt install nmap gobuster nuclei

# On Ubuntu/Debian:
sudo apt install nmap gobuster nuclei
```

#### 3. AI Agent Cannot Connect

```bash
# Verify MCP configuration paths
# Check server logs for connection attempts
python3 hexstrike_mcp.py --debug
```

#### 4. Redis Connection Issues

```bash
# Check if Redis is running
redis-cli ping

# Start Redis if not running
sudo systemctl start redis-server

# Enable Redis on boot
sudo systemctl enable redis-server
```

#### 5. Telegram Bot Not Responding

```bash
# Verify bot token and chat ID in .env
cat .env | grep TELEGRAM

# Test bot connection
curl -s "https://api.telegram.org/bot<TOKEN>/getMe"
```

#### 6. Permission Denied on Port Scan

```bash
# Run with sudo
sudo python3 daemon.py

# Or add capabilities to tools
sudo setcap cap_net_raw+ep $(which nmap)
sudo setcap cap_net_raw+ep $(which rustscan)
```

#### 7. WSL Networking Issues

```powershell
# From PowerShell (Admin)
wsl --shutdown
```

Then reopen WSL and restart the daemon.

#### 8. LLM API Errors

```bash
# Verify API key is set
echo $GOOGLE_API_KEY

# Test API connection
python3 -c "import litellm; print('OK')"

# Check inference logs
tail -f logs/daemon.log | grep inference
```

#### 9. SQLite Database Locked

```bash
# Only one daemon instance should run at a time
# Check for running processes
ps aux | grep daemon.py

# Kill existing instances
pkill -f daemon.py
```

### Debug Mode

Enable debug mode for detailed logging:

```bash
# MCP Server debug
python3 hexstrike_server.py --debug

# MCP Client debug
python3 hexstrike_mcp.py --debug

# Daemon debug
TG_LOG_LEVEL=DEBUG python3 daemon.py
```

### Log Files

- `logs/daemon.log` - Main daemon logs
- `logs/monitor.log` - Threat monitor logs
- `logs/token_log.db` - Token usage database

---

## Security Considerations

### ⚠️ Important Security Notes

- **Powerful System Access** - This tool provides AI agents with powerful system access to security tools
- **Isolated Environments** - Run in isolated environments or dedicated security testing VMs
- **Proper Oversight** - AI agents can execute arbitrary security tools - ensure proper oversight
- **Monitor Activities** - Monitor AI agent activities through the real-time dashboard and Telegram notifications
- **Authentication** - Consider implementing authentication for production deployments
- **Secure Configuration** - Protect `.env` file containing API keys and secrets
- **Network Exposure** - Be aware of exposed services when running in WSL or cloud environments

### Legal & Ethical Use

**✅ Authorized Use Cases:**
- Authorized penetration testing with proper written authorization
- Bug bounty programs within program scope and rules
- CTF competitions in educational and competitive environments
- Security research on owned or authorized systems
- Red team exercises with organizational approval
- Compliance and auditing on authorized infrastructure

**❌ Prohibited Use Cases:**
- Unauthorized testing of systems without permission
- Malicious activities or cybercrime
- Data theft or unauthorized data access
- Violation of any applicable laws or regulations

### Best Practices

1. **Always obtain written authorization** before testing any system
2. **Use isolated environments** for testing (VMs, dedicated networks)
3. **Monitor all activities** through logs and Telegram notifications
4. **Keep software updated** with the latest security patches
5. **Review and approve** dangerous operations via Telegram gates
6. **Secure your API keys** and never commit `.env` to version control
7. **Follow responsible disclosure** for any vulnerabilities discovered
8. **Document your testing** scope and obtain proper sign-off

---

## Contributing

We welcome contributions from the cybersecurity and AI community!

### Development Setup

```bash
# 1. Fork and clone the repository
git clone https://github.com/0x4m4/hexclaw.git
cd hexclaw

# 2. Create development environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install development dependencies
pip install -r requirements.txt

# 4. Start development server
python3 hexstrike_server.py --port 8888 --debug
```

### Priority Areas for Contribution

- **🤖 AI Agent Integrations** - Support for new AI platforms and agents
- **🛠️ Security Tool Additions** - Integration of additional security tools
- **⚡ Performance Optimizations** - Caching improvements and scalability enhancements
- **📖 Documentation** - AI usage examples and integration guides
- **🧪 Testing Frameworks** - Automated testing for AI agent interactions
- **🔌 New Skills** - YAML-based workflow definitions for common security tasks
- **🌐 Multi-language Support** - Internationalization and localization

### Contribution Guidelines

1. **Fork the repository** and create your feature branch
2. **Write clear, descriptive commit messages**
3. **Add tests** for new functionality
4. **Update documentation** as needed
5. **Submit a pull request** with a clear description of changes

### Code Style

- Follow PEP 8 for Python code
- Use type hints where appropriate
- Add docstrings to functions and classes
- Keep functions focused and modular
- Write clear, descriptive variable names

---

## License

MIT License - see LICENSE file for details.

---

## Author

**m0x4m4** - [www.0x4m4.com](https://www.0x4m4.com) | [HexClaw](https://www.hexclaw.com)

---

## Official Sponsor

<p align="center">
  <strong>Sponsored By LeaksAPI - Live Dark Web Data leak checker</strong>
</p>

<p align="center">
  <a href="https://leak-check.net">
    <img src="assets/leaksapi-logo.png" alt="LeaksAPI Logo" width="150" />
  </a>
  &nbsp;&nbsp;&nbsp;&nbsp;
  <a href="https://leak-check.net">
    <img src="assets/leaksapi-banner.png" alt="LeaksAPI Banner" width="450" />
  </a>
</p>

<p align="center">
  <a href="https://leak-check.net">
    <img src="https://img.shields.io/badge/Visit-leak--check.net-00D4AA?style=for-the-badge&logo=shield&logoColor=white" alt="Visit leak-check.net" />
  </a>
</p>

---

<div align="center">

## 🌟 Star History

[![Star History Chart](https://api.star-history.com/svg?repos=0x4m4/hexclaw&type=Date)](https://star-history.com/#0x4m4/hexclaw&Date)

### 📊 Project Statistics

- **150+ Security Tools** - Comprehensive security testing arsenal
- **12+ AI Agents** - Autonomous decision-making and workflow management
- **4000+ Vulnerability Templates** - Nuclei integration with extensive coverage
- **35+ Attack Categories** - From web apps to cloud infrastructure
- **Real-time Processing** - Sub-second response times with intelligent caching
- **99.9% Uptime** - Fault-tolerant architecture with graceful degradation

### 🚀 Ready to Transform Your Security Operations?

**[⭐ Star this repository](https://github.com/0x4m4/hexclaw)** • **[🍴 Fork and contribute](https://github.com/0x4m4/hexclaw/fork)** • **[📖 Read the docs](docs/)**

---

**Made with ❤️ by the cybersecurity community for AI-powered security automation**

*HexClaw v1.0 - Where artificial intelligence meets cybersecurity excellence*

</div>
