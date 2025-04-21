#!/bin/bash

# Detect operating system
detect_os() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        echo "linux"
    elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" || "$OSTYPE" == "cygwin" ]]; then
        echo "windows"
    else
        echo "unknown"
    fi
}

OS=$(detect_os)
echo "Detected operating system: $OS"

# Function to check if a command exists
command_exists() {
    command -v "$1" &> /dev/null
}

# Function to ensure python command exists
ensure_python_alias() {
    if command_exists python3 && ! command_exists python; then
        echo "python3 exists but python does not. Creating alias..."
        if [ "$OS" = "linux" ]; then
            if [ "$(id -u)" = "0" ]; then
                ln -s "$(which python3)" /usr/bin/python
            else
                echo "Need sudo privileges to create python alias. Please run:"
                echo "sudo ln -s \$(which python3) /usr/bin/python"
                exit 1
            fi
        elif [ "$OS" = "macos" ]; then
            # On macOS, we can create the alias in /usr/local/bin
            if [ "$(id -u)" = "0" ]; then
                ln -s "$(which python3)" /usr/local/bin/python
            else
                echo "Need sudo privileges to create python alias. Please run:"
                echo "sudo ln -s \$(which python3) /usr/local/bin/python"
                exit 1
            fi
        fi
        echo "Python alias created successfully."
    fi
}

# Function to ensure pip is installed
ensure_pip() {
    if ! command_exists pip && ! command_exists pip3; then
        echo "pip is not installed. Installing pip..."
        if [ "$OS" = "linux" ]; then
            if command_exists apt-get; then
                sudo apt-get update
                sudo apt-get install -y python3-pip
            elif command_exists yum; then
                sudo yum install -y python3-pip
            else
                echo "WARNING: Could not install pip automatically. Please install pip manually."
                exit 1
            fi
        elif [ "$OS" = "macos" ]; then
            if command_exists brew; then
                brew install python
            else
                echo "WARNING: Could not install pip automatically. Please install pip manually."
                exit 1
            fi
        fi
        echo "pip installed successfully."
    fi
}

# Function to install system dependencies
install_system_dependencies() {
    if [ "$OS" = "linux" ]; then
        if command_exists apt-get; then
            echo "Installing system dependencies..."
            sudo apt-get update
            sudo apt-get install -y portaudio19-dev python3-pyaudio
            echo "System dependencies installed successfully."
        elif command_exists yum; then
            echo "Installing system dependencies..."
            sudo yum install -y portaudio-devel python3-pyaudio
            echo "System dependencies installed successfully."
        fi
    fi
}

# Function to install Python audio packages
install_python_audio_packages() {
    echo "Installing Python audio packages..."
    pip install sounddevice
    echo "Python audio packages installed successfully."
}

# --- Install package manager and dependencies based on OS ---
install_dependencies() {
    case "$OS" in
        macos)
            # macOS: Use Homebrew
            if ! command_exists brew; then
                echo "Homebrew is not installed. Installing Homebrew..."
                /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
                eval "$(/opt/homebrew/bin/brew shellenv || /usr/local/bin/brew shellenv)"
                echo "Homebrew installed successfully."
            else
                echo "Homebrew is already installed."
            fi
            
            # Install tmux via Homebrew
            if ! command_exists tmux; then
                echo "Installing tmux..."
                brew install tmux
                echo "tmux installed successfully."
            else
                echo "tmux is already installed."
            fi
            
            # Install Node.js if needed
            if ! command_exists npm; then
                echo "Installing Node.js and npm..."
                brew install node
                echo "Node.js and npm installed successfully."
            else
                echo "npm is already installed."
            fi
            ;;
            
        linux)
            # Linux: Use apt-get, yum, or other package managers
            if command_exists apt-get; then
                # Debian/Ubuntu
                echo "Using apt-get package manager"
                
                if ! command_exists tmux; then
                    echo "Installing tmux..."
                    sudo apt-get update
                    sudo apt-get install -y tmux
                    echo "tmux installed successfully."
                else
                    echo "tmux is already installed."
                fi
                
                if ! command_exists npm; then
                    echo "Installing Node.js and npm..."
                    sudo apt-get update
                    sudo apt-get install -y nodejs npm
                    echo "Node.js and npm installed successfully."
                else
                    echo "npm is already installed."
                fi
            elif command_exists yum; then
                # RHEL/CentOS/Fedora
                echo "Using yum package manager"
                
                if ! command_exists tmux; then
                    echo "Installing tmux..."
                    sudo yum install -y tmux
                    echo "tmux installed successfully."
                else
                    echo "tmux is already installed."
                fi
                
                if ! command_exists npm; then
                    echo "Installing Node.js and npm..."
                    sudo yum install -y nodejs npm
                    echo "Node.js and npm installed successfully."
                else
                    echo "npm is already installed."
                fi
            else
                echo "WARNING: Unsupported Linux distribution. Please install tmux and Node.js manually."
            fi
            ;;
            
        windows)
            # Windows (WSL or Git Bash)
            echo "Windows detected. Please ensure you're running this in WSL or Git Bash."
            
            if command_exists apt-get; then
                # WSL with Ubuntu/Debian
                echo "Using apt-get package manager in WSL"
                
                if ! command_exists tmux; then
                    echo "Installing tmux..."
                    sudo apt-get update
                    sudo apt-get install -y tmux
                    echo "tmux installed successfully."
                else
                    echo "tmux is already installed."
                fi
                
                if ! command_exists npm; then
                    echo "Installing Node.js and npm..."
                    sudo apt-get update
                    sudo apt-get install -y nodejs npm
                    echo "Node.js and npm installed successfully."
                else
                    echo "npm is already installed."
                fi
            else
                echo "WARNING: Unable to detect package manager in Windows environment."
                echo "Please install tmux and Node.js manually."
            fi
            ;;
            
        *)
            echo "WARNING: Unsupported operating system. Please install tmux and Node.js manually."
            ;;
    esac
}

# Install OS-specific dependencies
install_dependencies

# Ensure python command exists
ensure_python_alias

# Ensure pip is installed
ensure_pip

# Install system dependencies
install_system_dependencies

# Install Python audio packages
install_python_audio_packages

# --- Install Python dependencies ---
echo "Installing Python dependencies..."
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt || python -m pip install -r requirements.txt
    echo "Python dependencies installed successfully."
else
    echo "Warning: requirements.txt not found. Skipping Python dependencies installation."
fi

# --- Install npm dependencies in electron_ui if needed ---
if [ -d "electron_ui" ]; then
    echo "Installing npm dependencies for electron_ui..."
    (cd electron_ui && npm install)
    echo "electron_ui dependencies installed successfully."
fi

# --- Kill existing session if it exists ---
tmux kill-session -t desktop-agent 2>/dev/null || true

# --- Create a new tmux session ---
echo "Starting application in tmux..."
tmux new-session -d -s desktop-agent -n "Desktop Agent"

# Set the name for the first pane (left)
tmux select-pane -t desktop-agent:0.0 -T "Daemon"

# Split the window vertically
tmux split-window -h -t desktop-agent

# Name the second pane (right)
tmux select-pane -t desktop-agent:0.1 -T "UI"

# Increase scrollback buffer (default is 2000 lines)
tmux set-option -g history-limit 10000

# Enable pane titles display
tmux set -g pane-border-status top
tmux set -g pane-border-format "#{pane_index}: #{pane_title}"

# Run daemon in the left pane
tmux send-keys -t desktop-agent:0.0 "echo 'Starting daemon...' && python -m launcher && python -m daemon | grep -v \"[Audio]\"" C-m

# Run UI in the right pane
tmux send-keys -t desktop-agent:0.1 "echo 'Starting UI...' && cd electron_ui && npm start" C-m

# Display tmux usage instructions
cat << EOF

=== DESKTOP AGENT APP STARTED ===

SCROLLING INSTRUCTIONS:
  - Press Ctrl+b then [ to enter scroll/copy mode
  - Use Page Up/Down, arrow keys, or mousewheel to scroll
  - Press q to exit scroll mode

NAVIGATION:
  - Ctrl+b then ← or → to switch between panes
  - Ctrl+b then d to detach (app keeps running)
  - tmux attach -t desktop-agent to reattach later
  - tmux kill-session -t desktop-agent to stop app

=================================

EOF

# Attach to the tmux session
echo "Starting tmux session..."
tmux attach-session -t desktop-agent

# Note: To detach from tmux without closing it, press Ctrl+b then d
# To reattach later: tmux attach -t desktop-agent
# To kill the session completely: tmux kill-session -t desktop-agent 