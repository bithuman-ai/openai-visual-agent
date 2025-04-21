document.addEventListener('DOMContentLoaded', () => {
    const tabs = document.querySelectorAll('.tab');
    const contents = document.querySelectorAll('.tab-content');
    const modelStatusBar = document.getElementById('modelStatusBar');
    const currentModelName = document.getElementById('currentModelName');
    const voiceStatusBar = document.getElementById('voiceStatusBar');
    const currentVoiceName = document.getElementById('currentVoiceName');
    const systemPromptsContainer = document.getElementById('systemPromptsContainer');
    const themeSwitch = document.getElementById('theme-switch');
    const modelsGrid = document.getElementById('modelsGrid');
    const revealButtons = document.querySelectorAll('.reveal-button');
    const bithumanLink = document.getElementById('openBithumanLink');

    // Global paths variables 
    let promptsPath, imagesPath, voicesPath, modelsPath;

    // ONCE ONLY: Request asset paths from main process
    console.log('Settings window loaded, requesting asset paths');
    require('electron').ipcRenderer.send('get-asset-paths');

    // Theme Toggle Functionality
    function initThemeToggle() {
        // Check for saved theme preference or use system preference
        const savedTheme = localStorage.getItem('theme');
        
        if (savedTheme === 'dark') {
            document.body.classList.add('dark-theme');
            themeSwitch.checked = true;
        } else if (savedTheme === 'light') {
            document.body.classList.remove('dark-theme');
            themeSwitch.checked = false;
        } else {
            // If no saved preference, check system preference
            const prefersDarkMode = window.matchMedia('(prefers-color-scheme: dark)').matches;
            if (prefersDarkMode) {
                document.body.classList.add('dark-theme');
                themeSwitch.checked = true;
            }
        }
        
        // Listen for theme toggle changes
        themeSwitch.addEventListener('change', () => {
            if (themeSwitch.checked) {
                document.body.classList.add('dark-theme');
                localStorage.setItem('theme', 'dark');
            } else {
                document.body.classList.remove('dark-theme');
                localStorage.setItem('theme', 'light');
            }
        });
        
        // Listen for system theme changes
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e => {
            // Only apply if user hasn't set a preference
            if (!localStorage.getItem('theme')) {
                if (e.matches) {
                    document.body.classList.add('dark-theme');
                    themeSwitch.checked = true;
                } else {
                    document.body.classList.remove('dark-theme');
                    themeSwitch.checked = false;
                }
            }
        });
    }
    
    // Initialize theme toggle
    initThemeToggle();

    // Listen for asset paths from main process with improved handling
    require('electron').ipcRenderer.on('asset-paths', (event, paths) => {
        console.log('Received asset paths from main process:', paths);
        
        // Store paths in global variables for later use
        if (paths) {
            // Using both global window variables and local variables
            window.imagesPath = imagesPath = paths.imagesPath || null;
            window.promptsPath = promptsPath = paths.promptsPath || null;
            window.voicesPath = voicesPath = paths.voicesPath || null;
            window.modelsPath = modelsPath = paths.modelsPath || null;
            
            console.log('Updated global path variables:');
            console.log('- promptsPath:', promptsPath);
            console.log('- imagesPath:', imagesPath);
            console.log('- voicesPath:', voicesPath);
            console.log('- modelsPath:', modelsPath);
            
            // Now that we have paths, load models and prompts
            loadPrompts();
            loadModels();
            
            // Show debug info in the UI (hidden by default)
            addDebugInfo(paths);
        } else {
            console.error('Received empty paths object from main process');
        }
    });

    // Add keyboard shortcut to close window (Escape key)
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            // Check if the model import modal is open
            const modelImportModal = document.getElementById('modelImportModal');
            if (modelImportModal && modelImportModal.classList.contains('show')) {
                // If the modal is open, close it instead of the settings window
                cancelModelImport();
            } else {
                // Otherwise save settings and close the window
                saveAllSettings();
                require('electron').ipcRenderer.send('close-settings-window');
            }
        } else if (e.ctrlKey && e.shiftKey && e.key === 'D') {
            // Hidden keyboard shortcut to toggle debug info
            const debugEl = document.getElementById('debug-paths');
            if (debugEl) {
                debugEl.style.display = debugEl.style.display === 'none' ? 'block' : 'none';
            }
        }
    });

    // Add event handler for save and close button
    document.getElementById('saveCloseButton').addEventListener('click', () => {
        console.log('Save and close button clicked');
        // Force save settings
        saveAllSettings();
        // Show a brief message to user
        const button = document.getElementById('saveCloseButton');
        const originalText = button.textContent;
        button.textContent = 'Saving and Applying...';
        button.disabled = true;
        
        // Add a short delay to make it clear something's happening
        setTimeout(() => {
            console.log('Closing settings window and applying changes');
            // Send close event to main process
            require('electron').ipcRenderer.send('close-settings-window');
        }, 500);
    });

    // Load prompts from JSON file
    loadPrompts();

    // Function to load prompts from JSON file with fallback paths
    function loadPrompts() {
        console.log('loadPrompts called, current promptsPath:', promptsPath);
        
        // Use a fallback path if global promptsPath isn't defined
        const attemptPromptsLoad = (promptsPathToUse) => {
            console.log('Attempting to load prompts from:', promptsPathToUse);
            
            try {
                const fs = require('fs');
                const path = require('path');
                const promptsPath = path.join(promptsPathToUse, 'prompts.json');
                
                console.log('Full prompts path:', promptsPath);
                
                // First check if file exists directly
                if (!fs.existsSync(promptsPath)) {
                    console.error(`Prompts file not found at: ${promptsPath}`);
                    return false;
                }
                
                // Read the file directly for robust handling
                try {
                    const data = JSON.parse(fs.readFileSync(promptsPath, 'utf8'));
                    console.log('Successfully loaded prompts.json:', data);
                    
                    if (data.systemPrompts && Array.isArray(data.systemPrompts)) {
                        populateSystemPrompts(data.systemPrompts);
                        return true;
                    } else {
                        console.error('Invalid prompts data format');
                        return false;
                    }
                } catch (readError) {
                    console.error('Error reading prompts file:', readError);
                    return false;
                }
            } catch (error) {
                console.error('Error in attemptPromptsLoad:', error);
                return false;
            }
        };
        
        // Wait for promptsPath to be defined by IPC before loading
        const checkPromptsPath = setInterval(() => {
            console.log('Checking for promptsPath... Current value:', promptsPath);
            
            if (typeof promptsPath !== 'undefined' && promptsPath) {
                clearInterval(checkPromptsPath);
                
                // Try loading from the IPC-provided path
                const success = attemptPromptsLoad(promptsPath);
                
                if (!success) {
                    // Try fallback path for macOS
                    console.log('Trying macOS fallback path');
                    const homedir = require('os').homedir();
                    const macPath = path.join(homedir, 'Library', 'Application Support', 'bitHumanVisualAgent', 'assets', 'prompts');
                    attemptPromptsLoad(macPath);
                }
            }
        }, 100); // Check every 100ms
        
        // Set a timeout in case promptsPath never gets defined
        setTimeout(() => {
            clearInterval(checkPromptsPath);
            if ((typeof promptsPath === 'undefined' || !promptsPath) && systemPromptsContainer) {
                console.log('Timeout reached, promptsPath not defined. Trying fallback paths...');
                
                // Try fallback paths for different OS platforms
                const homedir = require('os').homedir();
                const path = require('path');
                
                // Try macOS path first
                const macPath = path.join(homedir, 'Library', 'Application Support', 'bitHumanVisualAgent', 'assets', 'images', `${modelName}.jpg`);
                let success = attemptPromptsLoad(macPath);
                
                if (!success) {
                    console.error('All fallback attempts failed to load prompts');
                    systemPromptsContainer.innerHTML = `<div class="error-message">Error loading system prompts: All paths attempted failed</div>`;
                }
            }
        }, 5000); // Shorter timeout (5 seconds) since we have fallbacks
    }

    // Function to populate system prompts
    function populateSystemPrompts(prompts) {
        if (!systemPromptsContainer) return;
        
        // Clear container
        systemPromptsContainer.innerHTML = '';
        
        // Define the list of emojis for different prompt types
        const promptEmojis = {
            'scientist': '🔬',
            'teacher': '👩‍🏫',
            'coach': '🏆',
            'therapist': '🧠',
            'doctor': '⚕️',
            'tutor': '📚',
            'guide': '🧭',
            'chef': '👨‍🍳',
            'artist': '🎨',
            'writer': '✍️',
            'assistant': '🤖',
            'expert': '🧠',
            'historian': '📜',
            'storyteller': '📖',
            'advisor': '💼',
            'fitness': '💪',
            'nutritionist': '🥗',
            'programmer': '💻',
            'motivator': '🔥',
            'interviewer': '🎙️',
            'friend': '🤝',
            'mentor': '🌟',
            'advocate': '⚖️',
            'default': '💬'
        };
        
        // Assign appropriate emoji based on prompt title or content
        const getEmojiForPrompt = (prompt) => {
            const title = prompt.title.toLowerCase();
            const content = prompt.content.toLowerCase();
            
            for (const [type, emoji] of Object.entries(promptEmojis)) {
                if (title.includes(type) || content.includes(type)) {
                    return emoji;
                }
            }
            return promptEmojis.default;
        };
        
        // Add each prompt with animation delay
        prompts.forEach((prompt, index) => {
            const emoji = getEmojiForPrompt(prompt);
            const promptElement = document.createElement('div');
            promptElement.className = 'prompt-example';
            promptElement.setAttribute('data-prompt', prompt.id);
            promptElement.style.animationDelay = `${index * 0.1}s`;
            
            promptElement.innerHTML = `
                <div class="prompt-emoji">${emoji}</div>
                <h4>${prompt.title}</h4>
                <div class="description">${formatPromptContent(prompt.content)}</div>
                <button class="use-prompt-button">Use Template</button>
            `;
            
            systemPromptsContainer.appendChild(promptElement);
            
            // Add click event to the entire prompt example
            promptElement.addEventListener('click', () => {
                document.getElementById('systemPrompt').value = prompt.content;
                animatePromptSelection(promptElement);
            });
            
            // Add click event to the use template button
            const useButton = promptElement.querySelector('.use-prompt-button');
            useButton.addEventListener('click', (e) => {
                e.stopPropagation(); // Prevent triggering the parent click handler
                document.getElementById('systemPrompt').value = prompt.content;
                animatePromptSelection(promptElement);
            });
        });
    }
    
    // Function to animate the prompt selection
    function animatePromptSelection(promptElement) {
        // First, remove the highlight class from all prompts
        document.querySelectorAll('.prompt-example').forEach(el => {
            el.classList.remove('highlight-selected');
        });
        
        // Add the highlight class to the selected prompt
        promptElement.classList.add('highlight-selected');
        
        // Animate the prompt text area
        const promptTextarea = document.getElementById('systemPrompt');
        promptTextarea.classList.add('highlight-updated');
        
        // Smoothly scroll to the textarea
        promptTextarea.scrollIntoView({ behavior: 'smooth', block: 'center' });
        
        // Focus on the textarea
        promptTextarea.focus();
        
        // Remove the highlight classes after animation completes
        setTimeout(() => {
            promptElement.classList.remove('highlight-selected');
            promptTextarea.classList.remove('highlight-updated');
        }, 1500);
    }
    
    // Function to format prompt content for display
    function formatPromptContent(content) {
        return content.replace(/\n/g, '<br>');
    }
    
    // Tab switching
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            // Remove active class from all tabs and contents
            tabs.forEach(t => t.classList.remove('active'));
            contents.forEach(c => c.classList.remove('active'));

            // Add active class to clicked tab and corresponding content
            tab.classList.add('active');
            const tabId = tab.getAttribute('data-tab');
            document.getElementById(tabId).classList.add('active');
            
            // Load voices when voice tab is clicked
            if (tabId === 'voice') {
                loadVoices();
            }
        });
    });

    // MODELS TAB FUNCTIONALITY
    // Model selection
    const modelItems = document.querySelectorAll('.model-item');
    let selectedModel = null;

    modelItems.forEach(item => {
        item.addEventListener('click', () => {
            // Remove selected class from previous selection
            if (selectedModel) {
                selectedModel.classList.remove('selected');
            }
            
            // Add selected class to current selection
            item.classList.add('selected');
            selectedModel = item;
            
            // Update status bar
            const modelName = item.getAttribute('data-model');
            updateCurrentModel(modelName);
            
            // Send selected model to main process and save settings
            require('electron').ipcRenderer.send('select-model', modelName);
            saveAllSettings();
        });
    });

    // Initialize with current model if available
    // This should be called when settings window is opened to show current selection
    require('electron').ipcRenderer.on('current-model', (event, modelName) => {
        if (modelName) {
            const modelItem = document.querySelector(`.model-item[data-model="${modelName}"]`);
            if (modelItem) {
                modelItem.classList.add('selected');
                selectedModel = modelItem;
                updateCurrentModel(modelName);
            }
        }
    });

    // Function to convert a path to a file:// URL
    function pathToFileUrl(filePath) {
        return 'file://' + filePath.replace(/\\/g, '/');
    }

    // Function to check if file exists
    function fileExists(filePath) {
        try {
            const fs = require('fs');
            return fs.existsSync(filePath);
        } catch (err) {
            console.error(`Error checking if file exists: ${filePath}`, err);
            return false;
        }
    }

    // Function to update the current model display
    function updateCurrentModel(modelName) {
        if (!modelName) {
            console.error('Missing model name in updateCurrentModel');
            return;
        }
        
        console.log('Updating current model display for:', modelName);
        
        const displayName = modelName
            .split('_')
            .map(word => word.charAt(0).toUpperCase() + word.slice(1))
            .join(' ');
        
        // Get image path using multiple fallback strategies
        let imagePath = null;
        
        // Track if we found a valid image
        let imageFound = false;

        // Try different approaches to find the image in order of preference
        const path = require('path');
        const fs = require('fs');
        
        // Approach 1: Use imagesPath from IPC if available
        if (typeof imagesPath !== 'undefined' && imagesPath) {
            imagePath = path.join(imagesPath, `${modelName}.jpg`);
            console.log('Trying image path from IPC:', imagePath);
            if (fs.existsSync(imagePath)) {
                console.log('Found image at IPC path');
                imageFound = true;
            }
        }
        
        // Approach 2: Try macOS standard path if image not found yet
        if (!imageFound) {
            const homedir = require('os').homedir();
            const macPath = path.join(homedir, 'Library', 'Application Support', 'bitHumanVisualAgent', 'assets', 'images', `${modelName}.jpg`);
            console.log('Trying macOS standard path:', macPath);
            if (fs.existsSync(macPath)) {
                imagePath = macPath;
                imageFound = true;
                console.log('Found image at macOS standard path');
            }
        }
        
        // Approach 3: Try project-relative fallback path
        if (!imageFound) {
            const projectRoot = path.resolve(__dirname, '../../../../../');
            const projectPath = path.join(projectRoot, `assets/images/${modelName}.jpg`);
            console.log('Trying project-relative path:', projectPath);
            if (fs.existsSync(projectPath)) {
                imagePath = projectPath;
                imageFound = true;
                console.log('Found image at project-relative path');
            } else {
                console.error('No image found for model:', modelName);
                // We'll continue even without an image
            }
        }
        
        // Convert to file URL for browser compatibility if we found an image
        const imageUrl = imageFound ? pathToFileUrl(imagePath) : '';
        console.log('Final image URL:', imageUrl || 'None found');
        
        // Update the UI
        const currentModelName = document.getElementById('currentModelName');
        if (currentModelName) {
            if (imageUrl) {
                currentModelName.innerHTML = `<img src="${imageUrl}" alt="${displayName}" onerror="this.src='../img/model-placeholder.png'"> ${displayName}`;
            } else {
                // Use a placeholder image if no model image was found
                currentModelName.innerHTML = `<img src="../img/model-placeholder.png" alt="${displayName}"> ${displayName}`;
            }
            
            // Enable status indicator
            const modelStatusBar = document.getElementById('modelStatusBar');
            if (modelStatusBar) {
                modelStatusBar.classList.add('active');
            }
            
            // Save the current model name to localStorage
            localStorage.setItem('currentModelName', modelName);
        } else {
            console.error('currentModelName element not found in the DOM');
        }
    }

    // Add model button functionality
    const addModelButton = document.getElementById('addModelButton');
    addModelButton.addEventListener('click', () => {
        require('electron').ipcRenderer.send('open-file-dialog', { 
            filters: [
                { name: 'IMX Files', extensions: ['imx'] }
            ]
        });
    });

    // PROMPT TAB FUNCTIONALITY
    // Auto-save prompt when changed
    document.getElementById('systemPrompt').addEventListener('change', () => {
        saveAllSettings();
    });
    document.getElementById('systemPrompt').addEventListener('blur', () => {
        saveAllSettings();
    });

    // VOICE TAB FUNCTIONALITY
    // Voice selection and playback
    const voiceGrid = document.querySelector('.voice-grid');
    let selectedVoice = null;
    let currentAudio = null;  // Track the currently playing audio

    // Function to create voice items
    function createVoiceItem(voiceName) {
        const voiceItem = document.createElement('div');
        voiceItem.className = 'voice-item';
        voiceItem.innerHTML = `
            <div class="voice-container">
                <div class="play-button">
                    <div class="play-button-inner">
                        <svg class="play-icon" viewBox="0 0 24 24">
                            <path d="M8 5v14l11-7z"/>
                        </svg>
                        <svg class="pause-icon" viewBox="0 0 24 24" style="display:none;">
                            <path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/>
                        </svg>
                    </div>
                    <div class="play-ripple"></div>
                </div>
                <div class="voice-name">${voiceName}</div>
                <div class="voice-action-hint">Click to select • Click button to preview</div>
                <div class="selection-indicator">
                    <svg class="checkmark-icon" viewBox="0 0 24 24">
                        <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41L9 16.17z"/>
                    </svg>
                </div>
            </div>
        `;

        const playButton = voiceItem.querySelector('.play-button');
        const playIcon = voiceItem.querySelector('.play-icon');
        const pauseIcon = voiceItem.querySelector('.pause-icon');

        // Play/pause button click handler
        playButton.addEventListener('click', (e) => {
            e.stopPropagation(); // Prevent the cell click event from firing
            
            // Is this button currently in playing state?
            const isPlaying = playButton.classList.contains('playing');
            
            if (isPlaying) {
                // If playing, stop it
                if (currentAudio) {
                    currentAudio.pause();
                    currentAudio.currentTime = 0;
                    currentAudio = null;
                }
                
                // Update UI - show play icon
                playIcon.style.display = 'block';
                pauseIcon.style.display = 'none';
                playButton.classList.remove('playing');
            } else {
                // If not playing, start playback
                
                // First stop any other playing audio and reset UI
                document.querySelectorAll('.play-button').forEach(btn => {
                    if (btn !== playButton && btn.classList.contains('playing')) {
                        btn.classList.remove('playing');
                        const pi = btn.querySelector('.play-icon');
                        const pa = btn.querySelector('.pause-icon');
                        if (pi && pa) {
                            pi.style.display = 'block';
                            pa.style.display = 'none';
                        }
                    }
                });
                
                // Stop current audio if any
                if (currentAudio) {
                    currentAudio.pause();
                    currentAudio.currentTime = 0;
                }
                
                // Create and play new audio
                // Check if voicesPath is available from global variable
                let audioPath;
                if (window.voicesPath) {
                    // Use the global voicesPath
                    audioPath = path.join(window.voicesPath, `${voiceName}.wav`);
                    console.log(`Using global voicesPath for audio: ${audioPath}`);
                } else {
                    // Fallback to hardcoded path - this should not happen after our fixes
                    console.error('voicesPath global variable not found. Using fallback path.');
                    const projectRoot = path.resolve(__dirname, '../../../../');
                    audioPath = path.join(projectRoot, 'assets/voices', `${voiceName}.wav`);
                }
                
                console.log(`Playing voice audio from path: ${audioPath}`);
                
                // Check if the audio file exists before trying to play it
                if (fileExists(audioPath)) {
                    // Convert to file URL for browser compatibility
                    const audioUrl = pathToFileUrl(audioPath);
                    console.log(`Audio URL: ${audioUrl}`);
                    
                    currentAudio = new Audio(audioUrl);
                    currentAudio.play().catch(error => {
                        console.error(`Error playing audio for ${voiceName}:`, error);
                    });
                    
                    // Add ripple animation
                    const playRipple = voiceItem.querySelector('.play-ripple');
                    playRipple.classList.add('animate');
                    setTimeout(() => {
                        playRipple.classList.remove('animate');
                    }, 1000);
                } else {
                    console.error(`Audio file not found at path: ${audioPath}`);
                }
                
                // Update UI - show pause icon
                playIcon.style.display = 'none';
                pauseIcon.style.display = 'block';
                playButton.classList.add('playing');
                
                // Handle audio ending
                currentAudio.addEventListener('ended', () => {
                    playIcon.style.display = 'block';
                    pauseIcon.style.display = 'none';
                    playButton.classList.remove('playing');
                    currentAudio = null;
                });
            }
        });

        // Cell click handler - only for selection, not for audio playback
        voiceItem.addEventListener('click', () => {
            // Remove selected class from previous selection
            if (selectedVoice) {
                selectedVoice.classList.remove('selected');
            }
            
            // Add selected class to current selection
            voiceItem.classList.add('selected');
            selectedVoice = voiceItem;
            
            // Update status bar
            updateVoiceStatusBar(voiceName);
            
            // Send selected voice to main process and save settings
            require('electron').ipcRenderer.send('select-voice', voiceName);
            saveAllSettings();
            
            // Add selection animation
            const selectionIndicator = voiceItem.querySelector('.selection-indicator');
            selectionIndicator.classList.add('active');
            setTimeout(() => {
                selectionIndicator.classList.remove('active');
            }, 500);
        });

        return voiceItem;
    }

    // Function to update voice status bar
    function updateVoiceStatusBar(voiceName) {
        if (voiceName) {
            // Update status bar
            currentVoiceName.textContent = voiceName.charAt(0).toUpperCase() + voiceName.slice(1);
            voiceStatusBar.classList.add('active');
        } else {
            currentVoiceName.textContent = 'None selected';
            voiceStatusBar.classList.remove('active');
        }
    }

    // Function to load voices
    function loadVoices() {
        try {
            console.log('Loading voices...');
            
            // Clear existing grid
            voiceGrid.innerHTML = '';
            
            // Try to retrieve voices from the server
            fetch('http://localhost:' + (window.serverPort || '5001') + '/api/voices')
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`HTTP error! Status: ${response.status}`);
                    }
                    return response.json();
                })
                .then(data => {
                    console.log('Received voices from server:', data);
                    
                    // Use the available voices from the response
                    if (data && Array.isArray(data.voices)) {
                        data.voices.forEach(voice => {
                            // Handle both object format and string format
                            if (typeof voice === 'object' && voice.id) {
                                const voiceItem = createVoiceItem(voice.id);
                                voiceGrid.appendChild(voiceItem);
                            } else if (typeof voice === 'string') {
                                const voiceItem = createVoiceItem(voice);
                                voiceGrid.appendChild(voiceItem);
                            }
                        });
                    } else {
                        // Fallback to default voices
                        console.log('No voices from server, using defaults');
                        const defaultVoices = [
                            'alloy', 'ash', 'ballad', 'coral', 'echo', 
                            'sage', 'shimmer', 'verse'
                        ];
                        defaultVoices.forEach(voice => {
                            const voiceItem = createVoiceItem(voice);
                            voiceGrid.appendChild(voiceItem);
                        });
                    }
                })
                .catch(error => {
                    console.error('Error loading voices from API:', error);
                    
                    // Fallback to default voices
                    const defaultVoices = [
                        'alloy', 'ash', 'ballad', 'coral', 'echo', 
                        'sage', 'shimmer', 'verse'
                    ];
                    defaultVoices.forEach(voice => {
                        const voiceItem = createVoiceItem(voice);
                        voiceGrid.appendChild(voiceItem);
                    });
                });
        } catch (error) {
            console.error('Error loading voices:', error);
        }
    }

    // API KEYS FUNCTIONALITY
    // Initialize API key inputs with masked values
    function initializeApiKeyInputs() {
        const bithumanKeyInput = document.getElementById('bithumanKey');
        const openaiKeyInput = document.getElementById('openaiKey');
        
        // Request current keys from the main process
        require('electron').ipcRenderer.send('get-api-keys');
        
        // Listen for the response with the keys
        require('electron').ipcRenderer.on('api-keys', (event, keys) => {
            if (keys) {
                // Update both inputs with appropriately masked values
                if (keys.bithuman) {
                    // Store the original value in the dataset for reference when saving
                    bithumanKeyInput.dataset.originalValue = keys.bithuman;
                    // Display masked value
                    bithumanKeyInput.value = maskApiKey(keys.bithuman);
                    bithumanKeyInput.dataset.masked = 'true';
                    console.log('Initialized bitHuman API key (masked for display)');
                }
                
                if (keys.openai) {
                    // Store the original value in the dataset for reference when saving
                    openaiKeyInput.dataset.originalValue = keys.openai;
                    // Display masked value
                    openaiKeyInput.value = maskApiKey(keys.openai);
                    openaiKeyInput.dataset.masked = 'true';
                    console.log('Initialized OpenAI API key (masked for display)');
                }
            }
        });
    }
    
    // Function to mask an API key
    function maskApiKey(key) {
        if (!key) return '';
        
        // Keep first 4 and last 4 characters visible, mask the rest
        if (key.length <= 8) {
            return '*'.repeat(key.length);
        }
        
        return key.substring(0, 4) + '*'.repeat(key.length - 8) + key.substring(key.length - 4);
    }
    
    // Setup the reveal button functionality
    revealButtons.forEach(button => {
        const targetId = button.getAttribute('data-target');
        const targetInput = document.getElementById(targetId);
        
        if (targetInput) {
            button.addEventListener('click', () => {
                // Toggle between masked and unmasked
                if (targetInput.dataset.masked === 'true') {
                    // Show the original value
                    targetInput.type = 'text';
                    targetInput.value = targetInput.dataset.originalValue;
                    targetInput.dataset.masked = 'false';
                    // Change icon to 'hide'
                    updateRevealButtonIcon(button, 'hide');
                } else {
                    // Mask the value again
                    targetInput.type = 'password';
                    targetInput.value = maskApiKey(targetInput.dataset.originalValue);
                    targetInput.dataset.masked = 'true';
                    // Change icon to 'show'
                    updateRevealButtonIcon(button, 'show');
                }
            });
        }
    });
    
    // Update reveal button icon between show/hide states
    function updateRevealButtonIcon(button, state) {
        const icon = button.querySelector('.reveal-icon');
        
        if (state === 'hide') {
            // Change to hide (crossed-out eye) icon
            icon.innerHTML = `<path d="M12 7c2.76 0 5 2.24 5 5 0 .65-.13 1.26-.36 1.83l2.92 2.92c1.51-1.26 2.7-2.89 3.43-4.75-1.73-4.39-6-7.5-11-7.5-1.4 0-2.74.25-3.98.7l2.16 2.16C10.74 7.13 11.35 7 12 7zM2 4.27l2.28 2.28.46.46C3.08 8.3 1.78 10.02 1 12c1.73 4.39 6 7.5 11 7.5 1.55 0 3.03-.3 4.38-.84l.42.42L19.73 22 21 20.73 3.27 3 2 4.27zM7.53 9.8l1.55 1.55c-.05.21-.08.43-.08.65 0 1.66 1.34 3 3 3 .22 0 .44-.03.65-.08l1.55 1.55c-.67.33-1.41.53-2.2.53-2.76 0-5-2.24-5-5 0-.79.2-1.53.53-2.2zm4.31-.78l3.15 3.15.02-.16c0-1.66-1.34-3-3-3l-.17.01z"/>`;
            button.title = "Hide API Key";
            button.classList.add('showing');
            
            // Add a small animation to the button
            button.animate([
                { transform: 'translateY(-50%) scale(1)' },
                { transform: 'translateY(-50%) scale(1.1)' },
                { transform: 'translateY(-50%) scale(1)' }
            ], {
                duration: 300,
                easing: 'ease-in-out'
            });
        } else {
            // Change to show (eye) icon
            icon.innerHTML = `<path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/>`;
            button.title = "Show API Key";
            button.classList.remove('showing');
            
            // Add a small animation to the button
            button.animate([
                { transform: 'translateY(-50%) scale(1)' },
                { transform: 'translateY(-50%) scale(0.9)' },
                { transform: 'translateY(-50%) scale(1)' }
            ], {
                duration: 300,
                easing: 'ease-in-out'
            });
        }
    }
    
    // Call to initialize the API key inputs
    initializeApiKeyInputs();

    // Save API keys when they change
    document.getElementById('bithumanKey').addEventListener('change', (e) => {
        // Only save if the input is in unmasked state (editing the actual value)
        if (e.target.dataset.masked !== 'true') {
            const newValue = e.target.value;
            // Update the original value
            e.target.dataset.originalValue = newValue;
            
            // Send to main process
            require('electron').ipcRenderer.send('save-api-key', { 
                service: 'bithuman', 
                key: newValue 
            });
            saveAllSettings();
            
            // Remask after saving
            e.target.type = 'password';
            e.target.value = maskApiKey(newValue);
            e.target.dataset.masked = 'true';
            
            // Reset the reveal button icon
            const button = document.querySelector('.reveal-button[data-target="bithumanKey"]');
            if (button) {
                updateRevealButtonIcon(button, 'show');
            }
        }
    });

    document.getElementById('openaiKey').addEventListener('change', (e) => {
        // Only save if the input is in unmasked state (editing the actual value)
        if (e.target.dataset.masked !== 'true') {
            const newValue = e.target.value;
            // Update the original value
            e.target.dataset.originalValue = newValue;
            
            // Send to main process
            require('electron').ipcRenderer.send('save-api-key', { 
                service: 'openai', 
                key: newValue 
            });
            saveAllSettings();
            
            // Remask after saving
            e.target.type = 'password';
            e.target.value = maskApiKey(newValue);
            e.target.dataset.masked = 'true';
            
            // Reset the reveal button icon
            const button = document.querySelector('.reveal-button[data-target="openaiKey"]');
            if (button) {
                updateRevealButtonIcon(button, 'show');
            }
        }
    });

    // GLOBAL SETTINGS FUNCTIONALITY
    // Add window close handler to save settings before closing
    window.addEventListener('beforeunload', () => {
        saveAllSettings();
    });

    // Function to save all settings
    function saveAllSettings() {
        const settings = {};
        
        // Only add properties if they have a value
        if (selectedModel) {
            settings.model = selectedModel.getAttribute('data-model');
        }
        
        const promptValue = document.getElementById('systemPrompt').value;
        if (promptValue && promptValue.trim() !== '') {
            settings.prompt = promptValue;
        }
        
        if (selectedVoice) {
            settings.voice = selectedVoice.querySelector('.voice-name').textContent;
        }
        
        // Add API keys if they exist
        const bithumanKeyInput = document.getElementById('bithumanKey');
        const openaiKeyInput = document.getElementById('openaiKey');
        
        // Get the original (unmasked) API key values from the dataset properties
        const bithumanKey = bithumanKeyInput.dataset.originalValue || bithumanKeyInput.value;
        const openaiKey = openaiKeyInput.dataset.originalValue || openaiKeyInput.value;
        
        if (bithumanKey || openaiKey) {
            settings.apiKeys = {};
            if (bithumanKey) {
                settings.apiKeys.bithuman = bithumanKey;
            }
            if (openaiKey) {
                settings.apiKeys.openai = openaiKey;
            }
        }
        
        // Only send if we have settings to save
        if (Object.keys(settings).length > 0) {
            require('electron').ipcRenderer.send('save-all-settings', settings);
        }
    }

    // EVENTS FROM MAIN PROCESS
    // Handle file selection for model import
    require('electron').ipcRenderer.on('file-selected', (event, filePath) => {
        if (filePath) {
            console.log('Selected model file:', filePath);
            
            // Check if the file exists and is accessible
            try {
                const fs = require('fs');
                const fileStats = fs.statSync(filePath);
                
                if (!fileStats.isFile()) {
                    console.error('Selected path is not a file:', filePath);
                    return;
                }
                
                if (fileStats.size === 0) {
                    console.error('Selected file is empty:', filePath);
                    return;
                }
                
                // Show loading state and begin import
                showLoadingState('Generating preview...');
            require('electron').ipcRenderer.send('import-model', filePath);
                
            } catch (error) {
                console.error('Error accessing selected file:', error);
                // Show error message to user
                showErrorMessage(`Cannot access selected file: ${error.message}`);
            }
        }
    });

    // Handle models sync from main process
    require('electron').ipcRenderer.on('models-updated', (event, models) => {
        console.log('Received models update from main process:', models);
        if (models && models.length > 0) {
            populateModels(models);
        }
    });
    
    // Handle models from filesystem
    require('electron').ipcRenderer.on('models-from-filesystem', (event, models) => {
        console.log('Received models from filesystem:', models);
        if (models && models.length > 0) {
            populateModels(models);
        }
    });

    // Import model preview handling
    let currentModelImport = null;
    
    // Function to handle model import (move or copy)
    function importModel(action) {
        if (!currentModelImport) return;
        
        const shouldDelete = action === 'move';
        const actionName = shouldDelete ? 'Moving' : 'Copying';
        
        showLoadingState(`${actionName} model to library...`);
        require('electron').ipcRenderer.send('confirm-model-import', {
            modelPath: currentModelImport.modelPath,
            coverPhotoPath: currentModelImport.coverPhotoPath,
            shouldDelete: shouldDelete
        });
    }
    
    // Handle model preview data from main process
    require('electron').ipcRenderer.on('show-model-preview', (event, data) => {
        hideLoadingState();
        
        // Validate incoming data
        if (!data || !data.coverPhotoPath || !data.modelPath || !data.modelName) {
            console.error('Invalid model preview data received:', data);
            showErrorMessage('Received invalid model data from server.');
            return;
        }
        
        // Store the current import data for later use
        currentModelImport = data;
        
        // Format the model name for display
        const displayName = data.modelName
            .split('_')
            .map(word => word.charAt(0).toUpperCase() + word.slice(1))
            .join(' ');
        
        // Set up the preview modal
        const modal = document.getElementById('modelImportModal');
        const nameElement = document.getElementById('modelPreviewName');
        const imageElement = document.getElementById('modelPreviewImage');
        
        // Update the modal content
        nameElement.textContent = displayName;
        
        // Safely set the image source
        try {
            const fs = require('fs');
            if (fs.existsSync(data.coverPhotoPath)) {
                imageElement.src = pathToFileUrl(data.coverPhotoPath);
                // Add error handler to the image
                imageElement.onerror = () => {
                    imageElement.src = '../img/model-placeholder.png';
                    console.error('Error loading model preview image');
                };
            } else {
                console.error('Cover photo file not found:', data.coverPhotoPath);
                imageElement.src = '../img/model-placeholder.png';
            }
        } catch (error) {
            console.error('Error setting preview image:', error);
            imageElement.src = '../img/model-placeholder.png';
        }
        
        // Show the modal
        modal.classList.add('show');
    });
    
    // Handle model import errors
    require('electron').ipcRenderer.on('model-import-error', (event, data) => {
        hideLoadingState();
        console.error('Model import error:', data.error);
        
        // Show error message to user
        showErrorMessage(`Import error: ${data.error}`);
        
        // Close the modal if it's open
        const modal = document.getElementById('modelImportModal');
        modal.classList.remove('show');
        
        // Reset current import data
        currentModelImport = null;
    });
    
    // Handle model import completion
    require('electron').ipcRenderer.on('model-import-complete', (event, data) => {
        hideLoadingState();
        console.log('Model import complete:', data);
        
        // Show success message
        showSuccessMessage(`Successfully imported model: ${data.modelName}`);
        
        // Close the modal
        const modal = document.getElementById('modelImportModal');
        modal.classList.remove('show');
        
        // Reset current import data
        currentModelImport = null;
        
        // Request a sync of all models across all windows
        console.log('Requesting model sync after import...');
        require('electron').ipcRenderer.send('sync-models');
        
        // Small delay before refreshing the models grid to ensure files are fully written
        setTimeout(() => {
            // Refresh the models grid to show the new model
            loadModels();
            
            // After a short additional delay, select the newly imported model
            setTimeout(() => {
                const newModelItem = document.querySelector(`.model-item[data-model="${data.modelName}"]`);
                if (newModelItem) {
                    // Simulate a click on the newly imported model to select it
                    newModelItem.click();
                    
                    // Scroll to the model and highlight it briefly
                    newModelItem.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    newModelItem.classList.add('highlight-new');
                    
                    // Remove highlight after animation completes
                    setTimeout(() => {
                        newModelItem.classList.remove('highlight-new');
                    }, 2000);
                }
            }, 500);
        }, 1000);
    });
    
    // Set up modal dialog buttons
    document.getElementById('moveModelButton').addEventListener('click', () => {
        importModel('move');
    });
    
    document.getElementById('copyModelButton').addEventListener('click', () => {
        importModel('copy');
    });
    
    // Close button in modal header
    document.querySelector('.close-button').addEventListener('click', () => {
        cancelModelImport();
    });
    
    // Helper function to cancel model import
    function cancelModelImport() {
        console.log('Canceling model import');
        
        // Close the modal without doing anything
        const modal = document.getElementById('modelImportModal');
        modal.classList.remove('show');
        
        // If we have a current import with a cover photo path, we should tell the
        // main process to clean it up
        if (currentModelImport && currentModelImport.coverPhotoPath) {
            require('electron').ipcRenderer.send('cleanup-temporary-files', {
                coverPhotoPath: currentModelImport.coverPhotoPath
            });
        }
        
        // Reset current import data
        currentModelImport = null;
    }
    
    // Helper function to show a loading state
    function showLoadingState(message) {
        // Create a loading overlay if it doesn't exist
        let loadingOverlay = document.getElementById('loadingOverlay');
        
        if (!loadingOverlay) {
            loadingOverlay = document.createElement('div');
            loadingOverlay.id = 'loadingOverlay';
            loadingOverlay.className = 'modal';
            loadingOverlay.innerHTML = `
                <div class="loading-container">
                    <div class="loading-spinner"></div>
                    <div class="loading-message">${message || 'Loading...'}</div>
                </div>
            `;
            document.body.appendChild(loadingOverlay);
        } else {
            // Update the message
            const messageElement = loadingOverlay.querySelector('.loading-message');
            if (messageElement) {
                messageElement.textContent = message || 'Loading...';
            }
        }
        
        // Show the overlay
        loadingOverlay.classList.add('show');
    }
    
    // Helper function to hide the loading state
    function hideLoadingState() {
        const loadingOverlay = document.getElementById('loadingOverlay');
        if (loadingOverlay) {
            loadingOverlay.classList.remove('show');
        }
    }
    
    // Helper function to show an error message
    function showErrorMessage(message) {
        const notification = document.createElement('div');
        notification.className = 'notification error';
        notification.innerHTML = `
            <div class="notification-content">
                <div class="notification-icon">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
                        <path d="M12 22C6.477 22 2 17.523 2 12S6.477 2 12 2s10 4.477 10 10-4.477 10-10 10zm0-2a8 8 0 1 0 0-16 8 8 0 0 0 0 16zm-1-5h2v2h-2v-2zm0-8h2v6h-2V7z" fill="#ff3b30"/>
                    </svg>
                </div>
                <div class="notification-message">${message}</div>
            </div>
            <button class="notification-close">&times;</button>
        `;
        
        document.body.appendChild(notification);
        
        // Add close button event
        notification.querySelector('.notification-close').addEventListener('click', () => {
            document.body.removeChild(notification);
        });
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (document.body.contains(notification)) {
                document.body.removeChild(notification);
            }
        }, 5000);
    }
    
    // Helper function to show a success message
    function showSuccessMessage(message) {
        const notification = document.createElement('div');
        notification.className = 'notification success';
        notification.innerHTML = `
            <div class="notification-content">
                <div class="notification-icon">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
                        <path d="M12 22C6.477 22 2 17.523 2 12S6.477 2 12 2s10 4.477 10 10-4.477 10-10 10zm0-2a8 8 0 1 0 0-16 8 8 0 0 0 0 16zm-.997-4L6.76 11.757l1.414-1.414 2.83 2.829 5.657-5.657 1.414 1.414L11.003 16z" fill="#34c759"/>
                    </svg>
                </div>
                <div class="notification-message">${message}</div>
            </div>
            <button class="notification-close">&times;</button>
        `;
        
        document.body.appendChild(notification);
        
        // Add close button event
        notification.querySelector('.notification-close').addEventListener('click', () => {
            document.body.removeChild(notification);
        });
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (document.body.contains(notification)) {
                document.body.removeChild(notification);
            }
        }, 5000);
    }

    // Load existing settings when the page loads
    require('electron').ipcRenderer.send('get-settings');
    require('electron').ipcRenderer.on('settings-data', (event, settings) => {
        // Populate settings in the UI
        if (settings) {
            // Populate model selection
            if (settings.model) {
                const modelItem = document.querySelector(`.model-item[data-model="${settings.model}"]`);
                if (modelItem) {
                    modelItem.click();
                } else {
                    // Just update the status bar if the model item isn't found
                    updateCurrentModel(settings.model);
                }
            }
            
            // Populate system prompt
            if (settings.prompt) {
                document.getElementById('systemPrompt').value = settings.prompt;
            }
            
            // Populate API keys - but validate them first to ensure we don't use masked values
            if (settings.apiKeys) {
                // Helper function to check if a key value appears to be masked
                const isMaskedKey = (key) => {
                    return key && typeof key === 'string' && key.includes('*') && key.match(/\*{4,}/);
                };
                
                // Only use API keys that don't appear to be masked
                if (settings.apiKeys.bithuman && !isMaskedKey(settings.apiKeys.bithuman)) {
                    const bithumanKeyInput = document.getElementById('bithumanKey');
                    bithumanKeyInput.dataset.originalValue = settings.apiKeys.bithuman;
                    bithumanKeyInput.value = maskApiKey(settings.apiKeys.bithuman);
                    bithumanKeyInput.dataset.masked = 'true';
                    console.log('Loaded valid bitHuman API key from settings (masked for display)');
                }
                
                if (settings.apiKeys.openai && !isMaskedKey(settings.apiKeys.openai)) {
                    const openaiKeyInput = document.getElementById('openaiKey');
                    openaiKeyInput.dataset.originalValue = settings.apiKeys.openai;
                    openaiKeyInput.value = maskApiKey(settings.apiKeys.openai);
                    openaiKeyInput.dataset.masked = 'true';
                    console.log('Loaded valid OpenAI API key from settings (masked for display)');
                }
            }
            
            // Handle voice selection when the voice tab is opened
            if (settings.voice) {
                // Store the voice name for when the tab is activated
                const storedVoice = settings.voice;
                
                // Update status bar immediately
                updateVoiceStatusBar(storedVoice);
                
                // Define a function to apply the voice selection when tab is visible
                const applyVoiceSelection = () => {
                    setTimeout(() => {
                        const voiceItems = document.querySelectorAll('.voice-item');
                        voiceItems.forEach(item => {
                            const voiceName = item.querySelector('.voice-name').textContent;
                            if (voiceName === storedVoice) {
                                // Simulate a click on the voice item to select it
                                item.classList.add('selected');
                                selectedVoice = item;
                            }
                        });
                    }, 100); // Small delay to ensure voices are loaded
                };
                
                // Check if the voice tab is currently active
                const voiceTab = document.querySelector('.tab[data-tab="voice"]');
                if (voiceTab.classList.contains('active')) {
                    applyVoiceSelection();
                }
                
                // Also set up a listener for when the user switches to the voice tab
                document.querySelector('.tab[data-tab="voice"]').addEventListener('click', applyVoiceSelection);
            }
        }
    });

    // Call the loadModels function when DOM is loaded
    loadModels();

    // Function to load models from database
    function loadModels() {
        try {
            console.log('Loading models from database...');
            
            // Check if modelsGrid exists
            if (!modelsGrid) {
                console.error('modelsGrid element not found!');
                return;
            }
            
            console.log('modelsGrid found:', modelsGrid);
            
            // Clear existing model grid
            modelsGrid.innerHTML = '';
            
            // Default models to show if all other methods fail (with timestamp)
            const defaultModels = [
                {
                    id: 'albert_einstein', 
                    name: 'Albert Einstein', 
                    createdAt: new Date('2023-01-01'),
                    modifiedAt: new Date('2023-01-01')
                }
            ];

            // First, directly request models from the main process
            console.log('Requesting models from main process...');
            require('electron').ipcRenderer.send('get-models-from-filesystem');
            
            // Also try filesystem-based loading for backup
            const filesystemModels = loadModelsFromFilesystem();
            
            if (filesystemModels && filesystemModels.length > 0) {
                // If filesystem models are found, use them
                console.log('Using models from filesystem, count:', filesystemModels.length);
                populateModels(filesystemModels);
            }
            
            // As a final fallback, try the API
            fetchModelsFromAPI().then(apiModels => {
                if (apiModels && apiModels.length > 0) {
                    // Only update if we have more models than currently displayed
                    const currentModelCount = document.querySelectorAll('.model-item').length;
                    if (apiModels.length > currentModelCount) {
                        console.log('API returned additional models, updating display');
                        populateModels(apiModels);
                    }
                }
            }).catch(err => {
                console.warn('API fetch failed:', err);
                // If we have no models at all, use default
                const currentModelCount = document.querySelectorAll('.model-item').length;
                if (currentModelCount === 0) {
                    populateModels(defaultModels);
                }
            });
        } catch (error) {
            console.error('Error in loadModels function:', error);
            
            // Emergency fallback - try to display something
            try {
                // Default models with timestamp
                const defaultModels = [
                    {
                        id: 'albert_einstein', 
                        name: 'Albert Einstein',
                        createdAt: new Date('2023-01-01'),
                        modifiedAt: new Date('2023-01-01')
                    }
                ];
                console.log('Using emergency fallback models');
                populateModels(defaultModels);
            } catch (e) {
                console.error('Even the fallback failed:', e);
            }
        }
    }
    
    // Function to fetch models from API
    async function fetchModelsFromAPI() {
        try {
            console.log('Fetching models from API...');
            console.log('Server port:', window.serverPort || '5001');
            
            const response = await fetch('http://localhost:' + (window.serverPort || '5001') + '/api/models');
            
            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }
            
            const data = await response.json();
            console.log('API response data:', data);
            
            if (data && Array.isArray(data.models) && data.models.length > 0) {
                console.log('Using models from API:', data.models);
                
                // Add timestamp information if not already present
                const enhancedModels = data.models.map(model => {
                    if (!model.modifiedAt) {
                        // If API didn't provide timestamps, try to get from filesystem
                        try {
                            const fs = require('fs');
                            const path = require('path');
                            
                            // Try to find the model file to get its stats
                            let modelPath = null;
                            if (window.modelsPath) {
                                modelPath = path.join(window.modelsPath, `${model.id}.imx`);
                            }
                            
                            if (modelPath && fs.existsSync(modelPath)) {
                                const stats = fs.statSync(modelPath);
                                model.modifiedAt = stats.mtime;
                                
                                // Only set createdAt if not already present
                                if (!model.createdAt) {
                                    model.createdAt = stats.birthtime || stats.mtime;
                                }
                            } else {
                                // If we can't find the file, use current time as fallback
                                const now = new Date();
                                model.modifiedAt = now;
                                
                                // Only set createdAt if not already present
                                if (!model.createdAt) {
                                    model.createdAt = now;
                                }
                            }
                        } catch (e) {
                            console.error('Error enhancing model with time data:', e);
                            // Use current time as fallback
                            const now = new Date();
                            model.modifiedAt = now;
                            
                            // Only set createdAt if not already present
                            if (!model.createdAt) {
                                model.createdAt = now;
                            }
                        }
                    }
                    return model;
                });
                
                return enhancedModels;
            } else {
                console.log('Invalid API response or no models found');
                return null;
            }
        } catch (error) {
            console.error('Error fetching models from API:', error);
            throw error;
        }
    }

    // Function to populate models with add button first
    function populateModels(models) {
        console.log('Populating models grid with:', models);
        
        try {
            // Check if modelsGrid exists
            if (!modelsGrid) {
                console.error('modelsGrid element not found!');
                return;
            }
            
            console.log('modelsGrid found:', modelsGrid);
            
            // Clear existing model grid
            modelsGrid.innerHTML = '';
            
            // Create and add the import button as the FIRST item
            const addModelButton = createAddModelButton();
            modelsGrid.appendChild(addModelButton);
            
            // Check if we have models to populate
            if (!models || models.length === 0) {
                console.log('No models to populate');
                return;
            }
            
            // Sort models by modification time (newest first)
            models.sort((a, b) => {
                // First try to sort by modification time
                if (a.modifiedAt && b.modifiedAt) {
                    return new Date(b.modifiedAt) - new Date(a.modifiedAt);
                } else if (a.createdAt && b.createdAt) {
                    return new Date(b.createdAt) - new Date(a.createdAt);
                }
                // Fallback to alphabetical by name
                return a.name.localeCompare(b.name);
            });
            
            console.log('Models sorted by newest first:', models.map(m => m.name));
            
            // Retrieve the current selected model from localStorage if available
            const currentSelectedModelId = localStorage.getItem('currentModelName');
            console.log('Current selected model from localStorage:', currentSelectedModelId);
            
            // Keep track of which models have been added to avoid duplicates
            const addedModelIds = new Set();
            
            // Add each model with animation index
            models.forEach((model, index) => {
                // Skip if this model ID is already in the grid
                if (addedModelIds.has(model.id)) {
                    console.log('Skipping duplicate model:', model.id);
                    return;
                }
                
                console.log('Adding model to grid:', model);
                addedModelIds.add(model.id);
                
                const modelElement = document.createElement('div');
                modelElement.className = 'model-item';
                modelElement.setAttribute('data-model', model.id);
                // Add animation index as CSS variable for staggered animations
                modelElement.style.setProperty('--item-index', index);
                
                // Get image path using the global imagesPath variable
                let imagePath;
                if (window.imagesPath) {
                    imagePath = path.join(window.imagesPath, `${model.id}.jpg`);
                    console.log('Using global imagesPath:', window.imagesPath);
                } else {
                    // Fallback - this should not happen after our fixes
                    console.error('imagesPath global variable not found. Using fallback path.');
                    const projectRoot = path.resolve(__dirname, '../../../../../');
                    imagePath = path.join(projectRoot, `assets/images/${model.id}.jpg`);
                }
                
                console.log(`Model ${model.id} image path:`, imagePath);
                
                // Check if image exists
                const imageExists = fileExists(imagePath);
                console.log(`Image exists at ${imagePath}: ${imageExists}`);
                
                // Convert to file URL for browser compatibility
                const imageUrl = imageExists ? pathToFileUrl(imagePath) : '';
                
                // Log the image URL for debugging
                if (imageUrl) {
                    console.log('Using image URL:', imageUrl);
                } else {
                    console.warn('No image URL available for model:', model.id);
                }
                
                modelElement.innerHTML = `
                    <img src="${imageUrl}" alt="${model.name}" onerror="this.src='../img/model-placeholder.png'">
                    <div class="model-name">
                        <span class="model-name-text">${model.name}</span>
                    </div>
                    ${model.id !== 'albert_einstein' ? 
                        `<div class="delete-model-button" title="Delete this model">
                            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="16" height="16">
                                <path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z" fill="currentColor"/>
                            </svg>
                        </div>` : ''}
                `;
                
                // Add to grid after the add button
                modelsGrid.appendChild(modelElement);
                console.log('Model added to grid:', model.id);
                
                // Re-select this model if it was previously selected
                if (model.id === currentSelectedModelId) {
                    modelElement.classList.add('selected');
                    selectedModel = modelElement;
                }
                
                // Add click event for model selection
                modelElement.addEventListener('click', (e) => {
                    // Skip if the delete button was clicked
                    if (e.target.closest('.delete-model-button')) {
                        return;
                    }

                    console.log('Model clicked:', model.id);
                    
                    // Remove selected class from previous selection
                    if (selectedModel) {
                        selectedModel.classList.remove('selected');
                    }
                    
                    // Add selected class to current selection
                    modelElement.classList.add('selected');
                    selectedModel = modelElement;
                    
                    // Update status bar
                    updateCurrentModel(model.id);
                    
                    // Send selected model to main process and save settings
                    require('electron').ipcRenderer.send('select-model', model.id);
                    saveAllSettings();
                });

                // Add delete button event (only for non-default models)
                if (model.id !== 'albert_einstein') {
                    const deleteButton = modelElement.querySelector('.delete-model-button');
                    if (deleteButton) {
                        deleteButton.addEventListener('click', (e) => {
                            e.stopPropagation(); // Prevent model selection when deleting
                            
                            // Confirm before deleting
                            const confirmDelete = confirm(`Are you sure you want to delete the model "${model.name}"?`);
                            if (confirmDelete) {
                                console.log(`Deleting model: ${model.id}`);
                                
                                // Check if this is the currently selected model
                                const isCurrentlySelected = modelElement.classList.contains('selected');
                                
                                // Send delete request to main process
                                require('electron').ipcRenderer.send('delete-model', {
                                    modelId: model.id,
                                    isSelected: isCurrentlySelected
                                });
                            }
                        });
                    }
                }
            });
            
            // Restore selection status bar if a model was re-selected
            if (selectedModel) {
                updateCurrentModel(selectedModel.getAttribute('data-model'));
            }
            
            console.log('Finished populating models grid with', addedModelIds.size, 'models');
        } catch (error) {
            console.error('Error in populateModels:', error);
        }
    }
    
    // Function to create the add model button with an emoji
    function createAddModelButton() {
        const button = document.createElement('div');
        button.className = 'add-model-button';
        button.id = 'addModelButton';
        button.innerHTML = '<div class="button-text">Import New Model</div>';
        
        // Add event listener
        button.addEventListener('click', () => {
            require('electron').ipcRenderer.send('open-file-dialog', { 
                filters: [
                    { name: 'IMX Files', extensions: ['imx'] }
                ]
            });
        });
        
        return button;
    }
    
    // Function to load models from filesystem
    function loadModelsFromFilesystem() {
        const fs = require('fs');
        const path = require('path');
        
        // Determine the models directory path
        let modelsDir;
        
        if (typeof imagesPath !== 'undefined') {
            // Use the asset paths provided by IPC
            modelsDir = imagesPath.replace(/images$/, 'models');
            console.log('Using models directory from IPC paths:', modelsDir);
        } else {
            // Fallback to estimated path
            modelsDir = path.resolve(__dirname, '../../../../../assets/models');
            console.log('Using fallback models directory:', modelsDir);
        }
        
        // Check if the directory exists
        if (fs.existsSync(modelsDir)) {
            try {
                console.log('Models directory exists, scanning for .imx files');
                
                // Get all .imx files in the directory
                const files = fs.readdirSync(modelsDir).filter(f => f.endsWith('.imx'));
                console.log('Found model files:', files);
                
                if (files.length > 0) {
                    // Create model objects from files with modification time
                    const models = files.map(file => {
                        const filePath = path.join(modelsDir, file);
                        const stats = fs.statSync(filePath);
                        const id = file.replace('.imx', '');
                        const displayName = id.split('_')
                            .map(word => word.charAt(0).toUpperCase() + word.slice(1))
                            .join(' ');
                        
                        // Also get the image file stats if it exists
                        let imageStats = null;
                        if (typeof imagesPath !== 'undefined' && imagesPath) {
                            const imagePath = path.join(imagesPath, `${id}.jpg`);
                            if (fs.existsSync(imagePath)) {
                                imageStats = fs.statSync(imagePath);
                            }
                        }
                        
                        // Use image modification time if available (since image is created/copied with model)
                        // otherwise fall back to model file time
                        const modTime = imageStats ? imageStats.mtime : stats.mtime;
                        console.log(`Model ${id} modification time: ${modTime}`);
                        
                        return {
                            id: id,
                            name: displayName,
                            file: filePath,
                            createdAt: stats.birthtime || modTime,
                            modifiedAt: modTime
                        };
                    });
                    
                    // Sort by modification time (newest first)
                    models.sort((a, b) => {
                        return new Date(b.modifiedAt) - new Date(a.modifiedAt);
                    });
                    
                    console.log('Created model objects from filesystem:', models);
                    return models;
                }
            } catch (e) {
                console.error('Error reading models directory:', e);
            }
        } else {
            console.warn('Models directory not found:', modelsDir);
        }
        
        return null;
    }

    // Function to add debug info to the UI (used when paths are received)
    function addDebugInfo(paths) {
        // Only add debug info if it doesn't already exist
        if (document.getElementById('debug-paths')) return;
        
        const debugInfo = document.createElement('div');
        debugInfo.id = 'debug-paths';
        debugInfo.style.cssText = 'position: fixed; bottom: 10px; right: 10px; background: rgba(0,0,0,0.7); color: white; padding: 5px; border-radius: 3px; font-size: 10px; z-index: 9999; display: none;';
        debugInfo.innerHTML = `
            <div>Images Path: ${paths.imagesPath || 'undefined'}</div>
            <div>Prompts Path: ${paths.promptsPath || 'undefined'}</div>
            <div>Voices Path: ${paths.voicesPath || 'undefined'}</div>
            <div>Models Path: ${paths.modelsPath || 'undefined'}</div>
        `;
        document.body.appendChild(debugInfo);
    }

    // Add the event handler for model deletion confirmation
    require('electron').ipcRenderer.on('model-deleted', (event, data) => {
        console.log('Model deletion result:', data);
        
        if (data.success) {
            // Show success notification
            showSuccessMessage(`Model "${data.modelName}" has been deleted.`);
            
            // If the deleted model was the selected one, update UI to show Albert Einstein is now selected
            if (data.wasSelected) {
                // Show notification that Albert Einstein is now selected
                showSuccessMessage('Albert Einstein is now the selected model.');
                
                // Find the Albert Einstein model in the grid and select it
                const albertModel = document.querySelector('.model-item[data-model="albert_einstein"]');
                if (albertModel) {
                    // Remove selected class from previous selection
                    if (selectedModel) {
                        selectedModel.classList.remove('selected');
                    }
                    
                    // Add selected class to Albert Einstein
                    albertModel.classList.add('selected');
                    selectedModel = albertModel;
                    
                    // Update status bar
                    updateCurrentModel('albert_einstein');
                }
            }
            
            // Refresh the models grid
            loadModels();
        } else {
            // Show error notification
            showErrorMessage(`Error deleting model: ${data.error}`);
        }
    });

    // Handle BitHuman website link click
    if (bithumanLink) {
        bithumanLink.addEventListener('click', (e) => {
            e.preventDefault();
            // Use IPC to open the link in the default browser
            require('electron').ipcRenderer.send('open-external-url', 'https://www.bithuman.io/');
        });
    }
}); 