/**
 * Customer Relations Assistant Front-End Client
 * Connects to the local backend, updates context, checks Ollama status,
 * and maintains conversation flow.
 */

document.addEventListener('DOMContentLoaded', () => {
  // Elements
  const messagesContainer = document.getElementById('messagesContainer');
  const chatForm = document.getElementById('chatForm');
  const messageInput = document.getElementById('messageInput');
  const sendBtn = document.getElementById('sendBtn');
  const clearChatBtn = document.getElementById('clearChatBtn');
  const refreshHealthBtn = document.getElementById('refreshHealthBtn');
  const resetContextBtn = document.getElementById('resetContextBtn');
  const toggleSidebarBtn = document.getElementById('toggleSidebarBtn');
  const closeChatBtn = document.getElementById('closeChatBtn');
  const expandChatBtn = document.getElementById('expandChatBtn');
  const expandIcon = document.getElementById('expandIcon');
  const compressIcon = document.getElementById('compressIcon');
  const sidebar = document.getElementById('sidebar');

  // Config inputs
  const companyNameInput = document.getElementById('companyName');
  const businessTypeInput = document.getElementById('businessType');
  const workingHoursInput = document.getElementById('workingHours');
  const locationInput = document.getElementById('location');
  const productsServicesInput = document.getElementById('productsServices');
  const additionalInfoInput = document.getElementById('additionalInfo');
  const ollamaUrlInput = document.getElementById('ollamaUrl');
  const ollamaModelInput = document.getElementById('ollamaModel');
  const headerCompanyName = document.getElementById('headerCompanyName');
  const headerActiveAgentBadge = document.getElementById('headerActiveAgentBadge');
  const headerActiveAgentBadgeText = document.getElementById('headerActiveAgentBadgeText');
  const headerActiveAgentDot = document.getElementById('headerActiveAgentDot');
  const headerActiveAgentRole = document.getElementById('headerActiveAgentRole');
  const chatHeader = document.querySelector('.chat-header');

  // Customer Auth Elements
  const customerAuthBtn = document.getElementById('customerAuthBtn');
  const customerAuthBtnText = document.getElementById('customerAuthBtnText');
  const customerModalBackdrop = document.getElementById('customerModalBackdrop');
  const customerModalCloseBtn = document.getElementById('customerModalCloseBtn');
  const customerLoginFormView = document.getElementById('customerLoginFormView');
  const customerProfileView = document.getElementById('customerProfileView');
  const customerLoginForm = document.getElementById('customerLoginForm');
  const custUsernameInput = document.getElementById('custUsernameInput');
  const custPasswordInput = document.getElementById('custPasswordInput');
  const customerLoginError = document.getElementById('customerLoginError');
  const customerSubmitLoginBtn = document.getElementById('customerSubmitLoginBtn');
  const loggedInCustomerName = document.getElementById('loggedInCustomerName');
  const loggedInCustomerContact = document.getElementById('loggedInCustomerContact');
  const customerLogoutBtn = document.getElementById('customerLogoutBtn');
  const customerChatsCountBadge = document.getElementById('customerChatsCountBadge');
  const customerPastChatsList = document.getElementById('customerPastChatsList');
  let currentCustomer = null;

  // Status elements
  const statusPill = document.getElementById('ollamaStatusPill');
  const statusText = document.getElementById('ollamaStatusText');

  // Multi-Agent Configuration
  const DEFAULT_AGENT = {
    id: 'receptionist',
    name: 'Kepler Concierge',
    role: 'Front Desk & Reception',
    theme_color: '#10b981',
    badge: '🌿 Front Desk',
    icon: 'fas fa-concierge-bell'
  };

  function updateActiveAgentUI(agent) {
    if (!agent) agent = DEFAULT_AGENT;
    
    // 1. Dynamic header background
    if (chatHeader && agent.theme_color) {
      chatHeader.style.background = agent.theme_color;
    }
    
    // 2. Active agent badge text & dot
    if (headerActiveAgentBadgeText) {
      headerActiveAgentBadgeText.textContent = agent.badge || agent.name;
    }
    if (headerActiveAgentDot && agent.theme_color) {
      headerActiveAgentDot.style.background = agent.theme_color;
    }
    
    // 3. Active agent role
    if (headerActiveAgentRole) {
      headerActiveAgentRole.textContent = agent.name;
    }

    // 4. Sidebar roster active item indicator
    document.querySelectorAll('.agent-roster-item').forEach(el => {
      el.classList.remove('active');
    });
    const activeRosterItem = document.getElementById(`roster-${agent.id}`);
    if (activeRosterItem) {
      activeRosterItem.classList.add('active');
    }
  }

  // State - always generate a fresh session ID on page load/refresh so the backend starts clean
  let sessionId = generateUUID();
  sessionStorage.setItem('cra_session_id', sessionId);
  let isAwaitingReply = false;
  let clientLastMessageCount = 0;
  let clientLivePollTimer = null;

  // Initialize
  checkHealth();
  checkCustomerAuth();
  updateActiveAgentUI(DEFAULT_AGENT);
  renderInitialGreeting();
  startClientLivePolling();

  // Clear Chat button
  if (clearChatBtn) {
    clearChatBtn.addEventListener('click', () => {
      sessionId = generateUUID();
      sessionStorage.setItem('cra_session_id', sessionId);
      clientLastMessageCount = 0;
      messagesContainer.innerHTML = '';
      renderInitialGreeting();
    });
  }

  // Close widget button (communicates with parent page)
  if (closeChatBtn) {
    closeChatBtn.addEventListener('click', () => {
      try {
        window.parent.postMessage({ type: 'CLOSE_CHAT' }, '*');
      } catch (e) {
        console.warn('Could not post CLOSE_CHAT to parent:', e);
      }
    });
  }

  // Expand / Fullscreen toggle button
  function toggleFullscreenIcons(full) {
    if (expandIcon && compressIcon) {
      expandIcon.style.display = full ? 'none' : 'block';
      compressIcon.style.display = full ? 'block' : 'none';
    }
  }

  if (expandChatBtn) {
    expandChatBtn.addEventListener('click', () => {
      const inIframe = window.self !== window.top;
      if (inIframe) {
        try {
          window.parent.postMessage({ type: 'TOGGLE_FULLSCREEN' }, '*');
        } catch (e) {
          window.open('/chat', '_blank');
        }
      } else {
        if (!document.fullscreenElement) {
          document.documentElement.requestFullscreen().catch(() => {});
          toggleFullscreenIcons(true);
        } else {
          document.exitFullscreen().catch(() => {});
          toggleFullscreenIcons(false);
        }
      }
    });
  }

  window.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'FULLSCREEN_STATE') {
      toggleFullscreenIcons(Boolean(event.data.isFullscreen));
    }
  });

  document.addEventListener('fullscreenchange', () => {
    toggleFullscreenIcons(Boolean(document.fullscreenElement));
  });

  // Update header on company name change
  companyNameInput.addEventListener('input', () => {
    headerCompanyName.textContent = `${companyNameInput.value.trim() || 'Kepler Tech'} Assistant`;
  });

  // Toggle sidebar on smaller screens or button click
  toggleSidebarBtn.addEventListener('click', () => {
    sidebar.classList.toggle('open');
  });

  // Multi-input Batching & Turn Management State
  let unansweredUserMessages = [];
  let multiInputDebounceTimer = null;
  let activeAbortController = null;
  const MULTI_INPUT_DEBOUNCE_MS = 1200; // Bundle multiple inputs within 1.2s into a single turn

  // Ensure typing indicator exists and stays at the bottom of the conversation
  function ensureTypingIndicator() {
    let el = document.getElementById('typingIndicator');
    if (!el) {
      el = showTypingIndicator();
    } else {
      messagesContainer.appendChild(el);
      scrollToBottom();
    }
    return el;
  }

  function removeTypingIndicator() {
    const el = document.getElementById('typingIndicator');
    if (el) el.remove();
  }

  // Quick test prompt chips
  document.querySelectorAll('.prompt-chip').forEach(btn => {
    btn.addEventListener('click', () => {
      const text = btn.getAttribute('data-text');
      if (text) {
        enqueueUserMessage(text);
      }
    });
  });

  // Listen for prompt messages from parent landing page
  window.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'SEND_PROMPT' && event.data.text) {
      const text = event.data.text.trim();
      if (text) {
        enqueueUserMessage(text);
      }
    }
  });

  // Chat Form submit: NEVER blocks the user from sending multiple inputs!
  chatForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const text = messageInput.value.trim();
    if (!text) return;
    enqueueUserMessage(text);
  });

  // Health check button
  refreshHealthBtn.addEventListener('click', () => {
    checkHealth();
  });

  // Reset context to defaults
  resetContextBtn.addEventListener('click', async () => {
    try {
      const res = await fetch('/api/config');
      const data = await res.json();
      if (data.company_context) {
        companyNameInput.value = data.company_context.company_name || '';
        businessTypeInput.value = data.company_context.business_type || '';
        workingHoursInput.value = data.company_context.working_hours || '';
        locationInput.value = data.company_context.location || '';
        productsServicesInput.value = data.company_context.products_services || '';
        additionalInfoInput.value = data.company_context.additional_info || '';
        headerCompanyName.textContent = `${companyNameInput.value} Assistant`;
      }
    } catch (err) {
      console.error('Error fetching config defaults:', err);
    }
  });

  // Reset conversation button
  clearChatBtn.addEventListener('click', async () => {
    if (multiInputDebounceTimer) clearTimeout(multiInputDebounceTimer);
    if (activeAbortController) {
      try { activeAbortController.abort(); } catch (e) {}
      activeAbortController = null;
    }
    unansweredUserMessages = [];
    isAwaitingReply = false;
    removeTypingIndicator();

    try {
      await fetch('/api/reset', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId })
      });
    } catch (err) {
      console.warn('Reset endpoint failed:', err);
    }
    sessionId = generateUUID();
    sessionStorage.setItem('cra_session_id', sessionId);
    messagesContainer.innerHTML = '';
    renderInitialGreeting();
  });

  // Render initial greeting matching clean BotPenguin reference
  function renderInitialGreeting() {
    updateActiveAgentUI(DEFAULT_AGENT);
    const company = companyNameInput.value.trim() || 'Kepler Tech';
    const welcomeMsg = `Hi! Welcome to ${company}, I'll be assisting you here today.`;
    appendMessage('bot', welcomeMsg, '', [], null, null, [], [], [], DEFAULT_AGENT);

    setTimeout(() => {
      const followUp = "How can I help you with your printing solutions or consumable needs today?";
      appendMessage('bot', followUp, '', [], null, null, [], [], [], DEFAULT_AGENT);
    }, 250);
  }

  // Non-blocking Enqueue: Immediately shows user message, keeps input box open, and queues for single bot answer
  function enqueueUserMessage(text) {
    if (!text) return;
    const cleanText = text.trim();
    if (!cleanText) return;

    // 1. Immediately append to chat UI as a user bubble
    appendMessage('user', cleanText);
    clientLastMessageCount++;
    messageInput.value = '';
    messageInput.focus();

    // 2. Add to unanswered turn buffer so all inputs are preserved until answered
    unansweredUserMessages.push(cleanText);

    // 3. Keep typing indicator active at the bottom
    ensureTypingIndicator();

    // 4. If an HTTP request was already in-flight for this session, abort it so it won't render an outdated reply
    if (activeAbortController) {
      try {
        activeAbortController.abort();
      } catch (e) {}
      activeAbortController = null;

      // Invalidate on server so server releases lock immediately
      fetch('/api/chat/cancel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId })
      }).catch(() => {});
    }

    // 5. Reset batch debounce timer
    if (multiInputDebounceTimer) {
      clearTimeout(multiInputDebounceTimer);
    }

    // Wait MULTI_INPUT_DEBOUNCE_MS after latest input to give user time to send corrections or extra details
    multiInputDebounceTimer = setTimeout(() => {
      dispatchPendingTurn();
    }, MULTI_INPUT_DEBOUNCE_MS);
  }

  // Dispatches all accumulated user inputs in a single API call for one coherent bot response
  async function dispatchPendingTurn() {
    if (unansweredUserMessages.length === 0) return;

    const messagesToSend = [...unansweredUserMessages];

    ensureTypingIndicator();
    isAwaitingReply = true;

    const companyContext = {
      company_name: companyNameInput.value.trim(),
      business_type: businessTypeInput.value.trim(),
      working_hours: workingHoursInput.value.trim(),
      location: locationInput.value.trim(),
      products_services: productsServicesInput.value.trim(),
      additional_info: additionalInfoInput.value.trim()
    };

    const combinedMessage = messagesToSend.join('\n');
    const payload = {
      message: combinedMessage,
      messages: messagesToSend,
      session_id: sessionId,
      company_context: companyContext,
      model: ollamaModelInput.value.trim(),
      ollama_base_url: ollamaUrlInput.value.trim()
    };

    activeAbortController = new AbortController();

    let data;
    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: activeAbortController.signal
      });

      if (response.ok) {
        data = await response.json();
        // Clear unanswered buffer now that this turn succeeded!
        unansweredUserMessages = [];
      } else if (response.status === 409) {
        // Superseded by newer turn, ignore silently
        return;
      } else if (response.status === 429) {
        // Server lock or rate limit momentary wait, retry once after 1.5s
        await new Promise(r => setTimeout(r, 1500));
        const retryResp = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
          signal: activeAbortController ? activeAbortController.signal : undefined
        });
        if (retryResp.ok) {
          data = await retryResp.json();
          unansweredUserMessages = [];
        } else if (retryResp.status === 409) {
          return;
        } else {
          removeTypingIndicator();
          appendMessage('bot', "I apologize, but I encountered an issue processing your message. Could you try asking again?", "System Alert", [], null, null, [], [], [], DEFAULT_AGENT);
          return;
        }
      } else {
        removeTypingIndicator();
        appendMessage('bot', "I apologize, but I encountered an issue processing your message. Could you try asking again?", "System Alert", [], null, null, [], [], [], DEFAULT_AGENT);
        return;
      }
    } catch (err) {
      if (err.name === 'AbortError') {
        // Cancelled because user sent a newer message, ignore
        return;
      }
      removeTypingIndicator();
      console.error('Network error during chat:', err);
      appendMessage('bot', "I'm having trouble connecting to the backend right now. Please ensure the server is active.", "Offline", [], null, null, [], [], [], DEFAULT_AGENT);
      return;
    } finally {
      if (!activeAbortController || !activeAbortController.signal.aborted) {
        activeAbortController = null;
      }
      if (unansweredUserMessages.length === 0) {
        isAwaitingReply = false;
        removeTypingIndicator();
      }
    }

    if (data) {
      try {
        const activeAgent = data.active_agent || DEFAULT_AGENT;
        updateActiveAgentUI(activeAgent);
        const sourceLabel = data.source === 'ollama' ? 'Ollama' : (data.source === 'rag_comparison_engine' ? 'RAG Comparison Engine' : (data.source === 'guardrail_rule' ? 'Commercial Guardrail' : (data.source === 'human_agent_queue' ? 'Live Sales Desk' : 'Rule Engine')));
        appendMessage(
          'bot',
          data.reply,
          sourceLabel,
          data.suggested_chips || [],
          data.nlp,
          data.grounding,
          data.retrieved_sources || [],
          data.product_cards || [],
          data.consumable_cards || [],
          activeAgent,
          data.comparison_data || null
        );
        if (data.customer && data.customer.logged_in) {
          setLoggedInCustomer(data.customer);
        }
        clientLastMessageCount++;
      } catch (renderErr) {
        console.error('Error rendering assistant reply:', renderErr);
      }
    }
  }

  // Live Sales Agent Background Polling
  function startClientLivePolling() {
    if (clientLivePollTimer) clearInterval(clientLivePollTimer);
    clientLivePollTimer = setInterval(pollForAgentMessages, 2500);
  }

  async function pollForAgentMessages() {
    if (!sessionId || isAwaitingReply) return;
    try {
      const res = await fetch(`/api/chat/poll?session_id=${encodeURIComponent(sessionId)}&last_count=${clientLastMessageCount}`);
      if (!res.ok) return;
      const data = await res.json();

      if (data.human_agent_active) {
        updateActiveAgentUI({
          id: 'live_sales_specialist',
          name: data.human_agent_name || 'Live Sales Specialist',
          role: 'Technical Sales Advisor',
          badge: `👨‍💼 ${data.human_agent_name || 'Sales Specialist'} (Live)`,
          theme_color: '#10b981'
        });
      }

      if (data.new_messages && data.new_messages.length > 0) {
        data.new_messages.forEach(msg => {
          if (msg.sender === 'agent') {
            appendMessage(
              'bot',
              msg.content,
              'Live Sales Advisor',
              [],
              null,
              null,
              [],
              [],
              [],
              {
                id: 'live_agent',
                name: msg.agent_name || 'Sales Specialist',
                badge: `👨‍💼 ${msg.agent_name || 'Sales Specialist'} (Live)`,
                theme_color: '#10b981'
              }
            );
          } else if (msg.role === 'system' && msg.event === 'agent_takeover') {
            const notice = document.createElement('div');
            notice.className = 'agent-system-notice';
            notice.style.cssText = 'text-align:center;margin:10px auto;font-size:11.5px;font-weight:600;color:#10b981;background:rgba(16,185,129,0.12);border:1px solid rgba(16,185,129,0.3);border-radius:20px;padding:5px 14px;max-width:85%;';
            notice.textContent = `👨‍💼 ${msg.content}`;
            messagesContainer.appendChild(notice);
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
          }
        });
      }
      if (typeof data.total_count === 'number' && data.total_count > clientLastMessageCount) {
        clientLastMessageCount = data.total_count;
      }
    } catch (err) {
      // background polling fails silently
    }
  }

  // Append a message bubble to the container
  function appendMessage(sender, text, meta = '', chips = [], nlpData = null, groundingData = null, ragSources = [], productCards = [], consumableCards = [], activeAgent = null, comparisonData = null) {
    const row = document.createElement('div');
    row.className = `message-row ${sender}`;

    const agent = activeAgent || DEFAULT_AGENT;
    const themeColor = agent.theme_color || '#10b981';

    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    if (sender === 'bot') {
      avatar.innerHTML = `<img src="/static/images/kepler-icon-transparent.png" alt="Kepler" class="bot-msg-avatar-img">`;
    } else {
      avatar.style.display = 'none';
    }

    const contentWrapper = document.createElement('div');
    contentWrapper.style.minWidth = '0';
    contentWrapper.style.width = '100%';

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    if (sender === 'bot') {
      bubble.style.borderLeftColor = themeColor;
    }
    
    function formatMarkdownTables(raw) {
      if (!raw || !raw.includes('|')) return raw;
      const tableBlockRegex = /((?:^[ \t]*\|[^\n]+\|[ \t]*(?:\r?\n|$))+)/gm;
      return raw.replace(tableBlockRegex, (match) => {
        const lines = match.trim().split(/\r?\n/).map(l => l.trim()).filter(Boolean);
        if (lines.length < 2) return match;
        let sepIdx = -1;
        for (let i = 0; i < Math.min(3, lines.length); i++) {
          if (/^\|[\s\-:|]+\|$/.test(lines[i])) {
            sepIdx = i;
            break;
          }
        }
        if (sepIdx === -1) return match;

        const headerLines = lines.slice(0, sepIdx);
        const rowLines = lines.slice(sepIdx + 1);

        let html = '<div class="table-responsive" style="overflow-x: auto; margin: 10px 0; border-radius: 8px; border: 1px solid #e2e8f0; background: #ffffff;">';
        html += '<table style="width: 100%; border-collapse: collapse; font-size: 0.8rem; text-align: left; line-height: 1.4;">';
        
        if (headerLines.length > 0) {
          html += '<thead style="background: #f1f5f9; border-bottom: 2px solid #cbd5e1;">';
          headerLines.forEach(h => {
            html += '<tr>';
            const cells = h.split('|').slice(1, -1);
            cells.forEach(c => {
              html += `<th style="padding: 8px 10px; font-weight: 600; color: #1e293b;">${c.trim()}</th>`;
            });
            html += '</tr>';
          });
          html += '</thead>';
        }

        html += '<tbody>';
        rowLines.forEach((r, idx) => {
          const bg = idx % 2 === 0 ? '#ffffff' : '#f8fafc';
          html += `<tr style="background: ${bg}; border-bottom: 1px solid #f1f5f9;">`;
          const cells = r.split('|').slice(1, -1);
          cells.forEach((c, cIdx) => {
            const isFirst = cIdx === 0;
            const weight = isFirst ? 'font-weight: 600; color: #334155;' : 'color: #475569;';
            html += `<td style="padding: 7px 10px; ${weight}">${c.trim()}</td>`;
          });
          html += '</tr>';
        });
        html += '</tbody></table></div>';
        return html;
      });
    }

    // Format markdown bold, italic, line breaks, URLs, emails, and [Options: ...] tags
    let formattedText = formatMarkdownTables(text || "")
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/\*([^*]+)\*/g, '<em>$1</em>')
      .replace(/\[([^\]]+)\]\((https?:\/\/[^\s\)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer" style="color: #1877f2; text-decoration: underline; font-weight: 500;">$1</a>')
      .replace(/(^|[^">])(https?:\/\/[^\s<]+)/g, '$1<a href="$2" target="_blank" rel="noopener noreferrer" style="color: #1877f2; text-decoration: underline; font-weight: 500;">$2</a>')
      .replace(/(?:\r\n|\r|\n)/g, '<br>')
      .replace(/<br>\s*(<div class="table-responsive")/g, '$1')
      .replace(/(<\/div>)\s*<br>/g, '$1');

    // Parse [Options: A | B | C] pills from assistant text
    let parsedChips = [...(chips || [])];
    const optionsMatch = formattedText.match(/\[(?:Options:\s*)?([A-Za-z0-9\s&,–\-\/\+]{2,}(?:\s*\|\s*[A-Za-z0-9\s&,–\-\/\+]{2,})+)\]/);
    if (optionsMatch) {
      const extractedPills = optionsMatch[1].split('|').map(p => p.trim()).filter(p => p.length > 0);
      parsedChips = extractedPills.length > 0 ? extractedPills : parsedChips;
      formattedText = formattedText.replace(optionsMatch[0], '').trim();
    }

    if (sender === 'bot') {
      const tag = document.createElement('div');
      tag.className = 'message-agent-tag';
      tag.style.color = themeColor;
      tag.style.background = themeColor + '18'; // 10% opacity tint
      tag.innerHTML = `<span class="agent-dot" style="background: ${themeColor};"></span><span>${agent.badge || agent.name}</span>`;
      bubble.appendChild(tag);
      const textNode = document.createElement('div');
      textNode.className = 'bubble-text-content';
      textNode.innerHTML = formattedText;
      bubble.appendChild(textNode);
    } else {
      bubble.innerHTML = formattedText;
    }
    contentWrapper.appendChild(bubble);

    // Step 10: Multi-Card Product Grid Rendering
    if (sender === 'bot' && productCards && productCards.length > 0) {
      const cardsContainer = document.createElement('div');
      cardsContainer.className = 'catalogue-cards-block';

      const headerRow = document.createElement('div');
      headerRow.className = 'consumables-header-row';
      headerRow.innerHTML = `
        <div class="consumables-section-title">
          <span>🖨️ Verified Catalogue Matches (${productCards.length})</span>
        </div>
      `;
      cardsContainer.appendChild(headerRow);

      const grid = document.createElement('div');
      grid.className = 'product-cards-grid';

      productCards.forEach(p => {
        const card = document.createElement('div');
        card.className = 'product-card-item';
        const cardImg = p.image_url || '/static/images/printer-placeholder.svg';
        const cardUrl = p.product_url || p.website_url || 'https://www.keplertechllc.com/';
        const modelName = p.model || p.display_name || p.name || 'Catalogue Printer';
        const categoryLabel = p.category || 'Printing Equipment';
        const subcategoryLabel = p.subcategory || '';

        // Match reasons list
        const reasonsHtml = (p.match_reasons && p.match_reasons.length > 0)
          ? `<ul class="card-reasons-list">${p.match_reasons.map(r => `<li>${r}</li>`).join('')}</ul>`
          : '';

        // Available configurations badge
        const configsHtml = (p.available_configurations && p.available_configurations.length > 0)
          ? `<div class="card-configs-badge">⚙️ Configurations: ${p.available_configurations.join(', ')}</div>`
          : '';

        // Price details
        let priceHtml = '';
        if (p.price && !p.is_request) {
          const formatted = p.price_str || p.price_formatted || `AED ${Number(p.price).toLocaleString('en-US', {minimumFractionDigits: 2})}`;
          const vat = p.vat_note || '(Excl. VAT)';
          priceHtml = `
            <div class="card-price-row">
              <span class="card-price-val">${formatted}</span>
              <span class="card-price-vat">${vat}</span>
            </div>
          `;
        } else if (p.price_str && p.price_str !== 'Price on Request') {
          priceHtml = `
            <div class="card-price-row">
              <span class="card-price-val">${p.price_str}</span>
              ${p.vat_note ? `<span class="card-price-vat">${p.vat_note}</span>` : ''}
            </div>
          `;
        } else {
          priceHtml = `
            <div class="card-price-row">
              <span class="card-price-request">Commercial Quote on Request</span>
            </div>
          `;
        }

        card.innerHTML = `
          <div class="card-img-wrap" title="Click to view image">
            <img src="${cardImg}" alt="${modelName}" loading="lazy" referrerpolicy="no-referrer" onerror="this.onerror=null; this.src='/static/images/printer-placeholder.svg';">
          </div>
          <div class="card-badge-row">
            <span class="card-cat-badge">${subcategoryLabel || categoryLabel}</span>
          </div>
          <div class="card-title" title="${modelName}">${modelName}</div>
          ${priceHtml}
          ${configsHtml}
          ${reasonsHtml}
          <div class="card-actions-row">
            <a href="${cardUrl}" target="_blank" rel="noopener noreferrer" class="card-action-btn btn-view-details">
              View Details ↗
            </a>
            <button type="button" class="btn-compare-check" data-model="${modelName}" data-id="${p.id}">
              <span class="compare-box">☐</span> Compare
            </button>
          </div>
        `;

        // Compare action
        const compareBtn = card.querySelector('.btn-compare-check');
        compareBtn.addEventListener('click', () => {
          if (!window.selectedForComparison) {
            window.selectedForComparison = new Map();
          }
          if (window.selectedForComparison.has(p.id)) {
            window.selectedForComparison.delete(p.id);
            compareBtn.classList.remove('selected');
            compareBtn.querySelector('.compare-box').textContent = '☐';
          } else {
            window.selectedForComparison.set(p.id, modelName);
            compareBtn.classList.add('selected');
            compareBtn.querySelector('.compare-box').textContent = '☑';
          }
          updateComparisonBar();
        });

        grid.appendChild(card);
      });

      cardsContainer.appendChild(grid);
      contentWrapper.appendChild(cardsContainer);
    }

    // Comparison table / mobile cards
    if (sender === 'bot' && comparisonData && comparisonData.criteria && comparisonData.criteria.length > 0) {
      const compWrap = document.createElement('div');
      compWrap.className = 'inline-comparison-wrapper';
      if (typeof window.renderComparison === 'function') {
        window.renderComparison(comparisonData, compWrap);
      } else if (typeof window.renderInlineComparison === 'function') {
        compWrap.innerHTML = window.renderInlineComparison(comparisonData);
      }
      contentWrapper.appendChild(compWrap);
    }

    // Compatible Consumables Deck
    if (consumableCards && consumableCards.length > 0 && sender === 'bot') {
      const headerRow = document.createElement('div');
      headerRow.className = 'consumables-header-row';

      const titleEl = document.createElement('div');
      titleEl.className = 'consumables-section-title';
      titleEl.innerHTML = `<span>⚡ Compatible Inks & Consumables (${consumableCards.length})</span>`;
      headerRow.appendChild(titleEl);

      const navControls = document.createElement('div');
      navControls.className = 'carousel-header-controls';
      navControls.innerHTML = `
        <button type="button" class="deck-scroll-btn deck-prev" title="Scroll left">&#9664;</button>
        <button type="button" class="deck-scroll-btn deck-next" title="Scroll right">&#9654;</button>
      `;
      headerRow.appendChild(navControls);
      contentWrapper.appendChild(headerRow);

      const gridWrap = document.createElement('div');
      gridWrap.className = 'carousel-container-wrap';

      const grid = document.createElement('div');
      grid.className = 'consumables-grid';

      consumableCards.forEach(c => {
        const cCard = document.createElement('div');
        cCard.className = 'consumable-card';
        const cImg = c.image_url || c.image || 'https://www.keplertechllc.com/wp-content/uploads/2023/05/Kepler-Logo-.png';
        const cUrl = c.source_url || c.url || c.website_url || '#';
        const cTitle = c.title || c.name;

        let cPriceHtml = '';
        if (c.price) {
          const cFormatted = c.price_str || c.price_formatted || `AED ${Number(c.price).toLocaleString('en-US', {minimumFractionDigits: 2})}`;
          const cVat = c.vat_note || '(Excl. VAT)';
          cPriceHtml = `
            <div class="card-price-row" style="margin: 2px 0 4px;">
              <span class="card-price-val" style="font-size: 0.8rem;">${cFormatted}</span>
              <span class="card-price-vat" style="font-size: 0.65rem;">${cVat}</span>
            </div>
          `;
        } else if (c.price_str && c.price_str !== 'Price on Request') {
          cPriceHtml = `
            <div class="card-price-row" style="margin: 2px 0 4px;">
              <span class="card-price-val" style="font-size: 0.8rem;">${c.price_str}</span>
            </div>
          `;
        }

        cCard.innerHTML = `
          <div class="consumable-img-wrap" title="Click to enlarge">
            <img src="${cImg}" alt="${c.name}" loading="lazy" referrerpolicy="no-referrer" onerror="this.onerror=null; this.src='https://www.keplertechllc.com/wp-content/uploads/2023/05/Kepler-Logo-.png';">
          </div>
          <div class="consumable-title" title="${cTitle}">${cTitle}</div>
          <div class="consumable-sku">${c.sku}</div>
          ${cPriceHtml}
          <div class="consumable-actions" style="margin-top: auto; padding-top: 4px;">
            <a href="${cUrl}" target="_blank" class="card-btn" style="color: var(--chat-blue); font-size: 0.68rem; padding: 4px 6px; text-align: center; text-decoration: none; background: #f0f2f5;">
              View on Website ↗
            </a>
          </div>
        `;

        cCard.querySelector('.consumable-img-wrap').addEventListener('click', () => {
          openLightbox(cImg, `${c.name} (${c.sku})`);
        });

        grid.appendChild(cCard);
      });

      const prevHandler = () => grid.scrollBy({ left: -220, behavior: 'smooth' });
      const nextHandler = () => grid.scrollBy({ left: 220, behavior: 'smooth' });

      navControls.querySelector('.deck-prev').addEventListener('click', prevHandler);
      navControls.querySelector('.deck-next').addEventListener('click', nextHandler);

      // Horizontal wheel scrolling
      grid.addEventListener('wheel', (e) => {
        if (e.deltaY !== 0) {
          e.preventDefault();
          grid.scrollLeft += e.deltaY;
        }
      }, { passive: false });

      gridWrap.appendChild(grid);
      contentWrapper.appendChild(gridWrap);
    }

    // Metadata bar with NLP badges
    const metaEl = document.createElement('div');
    metaEl.className = 'message-meta';

    if (meta) {
      const sourceSpan = document.createElement('span');
      sourceSpan.textContent = meta;
      metaEl.appendChild(sourceSpan);
    }

    if (nlpData && sender === 'bot') {
      if (nlpData.intent) {
        const intentBadge = document.createElement('span');
        intentBadge.className = 'nlp-badge intent';
        intentBadge.textContent = nlpData.intent.replace(/_/g, ' ');
        metaEl.appendChild(intentBadge);
      }
      if (nlpData.corrections && nlpData.corrections.length > 0) {
        const typoBadge = document.createElement('span');
        typoBadge.className = 'nlp-badge correction';
        typoBadge.textContent = `Auto-corrected: ${nlpData.corrections[0]}`;
        metaEl.appendChild(typoBadge);
      }
    }

    if (groundingData && sender === 'bot' && groundingData.is_grounded) {
      const groundBadge = document.createElement('span');
      groundBadge.className = 'nlp-badge';
      groundBadge.textContent = '✓ 0 Hallucinations: Grounded';
      metaEl.appendChild(groundBadge);
    }

    // Render interactive quick reply chips
    if (sender === 'bot' && parsedChips && parsedChips.length > 0) {
      const chipsBar = document.createElement('div');
      chipsBar.className = 'quick-chips-inline';
      chipsBar.style.cssText = 'display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px;';
      parsedChips.forEach(chipText => {
        const chipBtn = document.createElement('button');
        chipBtn.type = 'button';
        chipBtn.className = 'prompt-chip';
        chipBtn.style.cssText = 'background: #ffffff; border: 1px solid #cbd5e1; border-radius: 14px; padding: 5px 12px; font-size: 0.74rem; cursor: pointer; color: #1e293b; font-weight: 500; transition: all 0.15s ease; box-shadow: 0 1px 2px rgba(0,0,0,0.05);';
        chipBtn.textContent = chipText;
        chipBtn.addEventListener('click', () => {
          if (chipText === '🔑 Open Login' || chipText === 'Open Login') {
            openCustomerModal();
            return;
          }
          enqueueUserMessage(chipText);
        });
        chipsBar.appendChild(chipBtn);
      });
      contentWrapper.appendChild(chipsBar);
    }

    row.appendChild(avatar);
    row.appendChild(contentWrapper);

    messagesContainer.appendChild(row);
    scrollToBottom();
  }

  // Show typing animation
  function showTypingIndicator() {
    const row = document.createElement('div');
    row.className = 'message-row bot';
    row.id = 'typingIndicator';

    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.innerHTML = `<img src="/static/images/kepler-icon-transparent.png" alt="Kepler" class="bot-msg-avatar-img">`;

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble typing-bubble';
    bubble.innerHTML = `
      <div class="typing-dot"></div>
      <div class="typing-dot"></div>
      <div class="typing-dot"></div>
    `;

    row.appendChild(avatar);
    row.appendChild(bubble);
    messagesContainer.appendChild(row);
    scrollToBottom();
    return row;
  }

  function scrollToBottom() {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  // Health check for Ollama
  async function checkHealth() {
    try {
      const res = await fetch('/api/health');
      const data = await res.json();
      if (data.online) {
        statusPill.className = 'status-pill';
        statusText.textContent = `Ollama: Online (${data.models ? data.models.length : 0} models)`;
      } else {
        statusPill.className = 'status-pill sim';
        statusText.textContent = 'Ollama: Standby (Simulator Ready)';
      }
    } catch (e) {
      statusPill.className = 'status-pill sim';
      statusText.textContent = 'Server connecting...';
    }
  }

  // Lightbox Modal Logic
  const lightboxModal = document.createElement('div');
  lightboxModal.className = 'image-lightbox-modal';
  lightboxModal.innerHTML = `
    <div class="lightbox-content">
      <button class="lightbox-close-btn">&times;</button>
      <div class="lightbox-img-box">
        <img src="" alt="Product Photo" id="lightboxImg">
      </div>
      <div class="lightbox-title" id="lightboxTitle"></div>
    </div>
  `;
  document.body.appendChild(lightboxModal);

  lightboxModal.querySelector('.lightbox-close-btn').addEventListener('click', () => {
    lightboxModal.classList.remove('open');
  });

  lightboxModal.addEventListener('click', (e) => {
    if (e.target === lightboxModal) {
      lightboxModal.classList.remove('open');
    }
  });

  function openLightbox(src, title) {
    document.getElementById('lightboxImg').src = src;
    document.getElementById('lightboxTitle').textContent = title || '';
    lightboxModal.classList.add('open');
  }

  function updateComparisonBar() {
    let bar = document.getElementById('comparisonFloatingBar');
    const count = window.selectedForComparison ? window.selectedForComparison.size : 0;

    if (count >= 2) {
      if (!bar) {
        bar = document.createElement('div');
        bar.id = 'comparisonFloatingBar';
        bar.className = 'comparison-floating-bar';
        document.body.appendChild(bar);
      }
      const modelNames = Array.from(window.selectedForComparison.values());
      bar.innerHTML = `
        <span>📊 Selected for Comparison: <strong>${modelNames.join(' vs ')}</strong></span>
        <button type="button" id="triggerComparisonBtn">Compare Now</button>
      `;
      bar.style.display = 'flex';

      document.getElementById('triggerComparisonBtn').onclick = () => {
        const query = `Compare ${modelNames.join(' and ')}`;
        bar.style.display = 'none';
        window.selectedForComparison.clear();
        document.querySelectorAll('.btn-compare-check').forEach(btn => {
          btn.classList.remove('selected');
          const box = btn.querySelector('.compare-box');
          if (box) box.textContent = '☐';
        });
        messageInput.value = query;
        sendMessage(query);
      };
    } else if (bar) {
      bar.style.display = 'none';
    }
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Customer Auth & Chat History Implementation
  // ──────────────────────────────────────────────────────────────────────────

  async function checkCustomerAuth() {
    try {
      const res = await fetch('/api/customer/auth/me');
      if (!res.ok) return;
      const data = await res.json();
      if (data.logged_in && data.customer) {
        setLoggedInCustomer(data.customer);
      } else {
        setLoggedOutCustomer();
      }
    } catch (e) {
      console.warn('Could not check customer auth status:', e);
    }
  }

  function setLoggedInCustomer(customer) {
    currentCustomer = customer;
    if (customerAuthBtn) {
      customerAuthBtn.classList.add('logged-in');
      if (customerAuthBtnText) {
        customerAuthBtnText.textContent = customer.name.split(' ')[0] || customer.name;
      }
    }
    if (loggedInCustomerName) loggedInCustomerName.textContent = customer.name;
    if (loggedInCustomerContact) loggedInCustomerContact.textContent = customer.phone || customer.email || 'Verified Customer';
    if (customerLoginFormView) customerLoginFormView.style.display = 'none';
    if (customerProfileView) customerProfileView.style.display = 'block';
  }

  function setLoggedOutCustomer() {
    currentCustomer = null;
    if (customerAuthBtn) {
      customerAuthBtn.classList.remove('logged-in');
      if (customerAuthBtnText) {
        customerAuthBtnText.textContent = 'Login';
      }
    }
    if (customerLoginFormView) customerLoginFormView.style.display = 'block';
    if (customerProfileView) customerProfileView.style.display = 'none';
  }

  if (customerAuthBtn) {
    customerAuthBtn.addEventListener('click', () => {
      if (currentCustomer) {
        openCustomerModal();
      } else {
        enqueueUserMessage("login");
      }
    });
  }

  if (customerModalCloseBtn) {
    customerModalCloseBtn.addEventListener('click', () => {
      closeCustomerModal();
    });
  }

  if (customerModalBackdrop) {
    customerModalBackdrop.addEventListener('click', (e) => {
      if (e.target === customerModalBackdrop) {
        closeCustomerModal();
      }
    });
  }

  function openCustomerModal() {
    if (customerLoginError) customerLoginError.style.display = 'none';
    if (currentCustomer) {
      loadCustomerPastChats();
    }
    if (customerModalBackdrop) {
      customerModalBackdrop.classList.add('open');
    }
  }

  function closeCustomerModal() {
    if (customerModalBackdrop) {
      customerModalBackdrop.classList.remove('open');
    }
  }

  if (customerLoginForm) {
    customerLoginForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const username = custUsernameInput.value.trim();
      const password = custPasswordInput.value.trim();
      if (!username || !password) return;

      if (customerSubmitLoginBtn) {
        customerSubmitLoginBtn.disabled = true;
        customerSubmitLoginBtn.textContent = 'Logging in...';
      }
      if (customerLoginError) customerLoginError.style.display = 'none';

      try {
        const res = await fetch('/api/customer/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            username: username,
            password: password,
            session_id: sessionId
          })
        });

        const data = await res.json();
        if (res.ok && data.success) {
          setLoggedInCustomer(data.customer);
          custPasswordInput.value = '';
          renderCustomerPastChats(data.sessions || []);
          appendMessage('bot', `Welcome back, **${data.customer.name}**! You are logged in. Your previous conversations and quotes are loaded. You can continue our chat or switch to a past conversation anytime using the profile button at the top.`, 'Customer Account', [], null, null, [], [], [], DEFAULT_AGENT);
        } else {
          if (customerLoginError) {
            customerLoginError.textContent = data.error || 'Invalid name or phone/email. Please try again.';
            customerLoginError.style.display = 'block';
          }
        }
      } catch (err) {
        if (customerLoginError) {
          customerLoginError.textContent = 'Connection error. Please try again.';
          customerLoginError.style.display = 'block';
        }
      } finally {
        if (customerSubmitLoginBtn) {
          customerSubmitLoginBtn.disabled = false;
          customerSubmitLoginBtn.textContent = 'Log In & Load Previous Chats';
        }
      }
    });
  }

  if (customerLogoutBtn) {
    customerLogoutBtn.addEventListener('click', async () => {
      try {
        await fetch('/api/customer/auth/logout', { method: 'POST' });
      } catch (e) {}
      setLoggedOutCustomer();
      closeCustomerModal();
    });
  }

  async function loadCustomerPastChats() {
    if (!customerPastChatsList) return;
    customerPastChatsList.innerHTML = '<div class="empty-chats-placeholder">Loading past conversations...</div>';
    try {
      const res = await fetch('/api/customer/sessions');
      if (!res.ok) throw new Error('Failed to fetch sessions');
      const data = await res.json();
      renderCustomerPastChats(data.sessions || []);
    } catch (e) {
      customerPastChatsList.innerHTML = '<div class="empty-chats-placeholder">Could not load past conversations.</div>';
    }
  }

  function renderCustomerPastChats(sessions) {
    if (!customerPastChatsList) return;
    if (customerChatsCountBadge) {
      customerChatsCountBadge.textContent = `${sessions.length} session${sessions.length === 1 ? '' : 's'}`;
    }
    if (!sessions || sessions.length === 0) {
      customerPastChatsList.innerHTML = '<div class="empty-chats-placeholder">No previous conversations found yet. Your current conversation is linked to your account!</div>';
      return;
    }

    customerPastChatsList.innerHTML = '';
    sessions.forEach(s => {
      const isCurrent = s.session_id === sessionId;
      const item = document.createElement('div');
      item.className = `past-chat-item ${isCurrent ? 'current-active' : ''}`;

      const dateStr = s.updated_at ? new Date(s.updated_at * 1000).toLocaleString(undefined, {
        month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
      }) : 'Past session';

      item.innerHTML = `
        <div class="past-chat-top">
          <span class="past-chat-date">${dateStr} ${isCurrent ? '• <strong>(Active)</strong>' : ''}</span>
          <span class="past-chat-turns">${s.turn_count || 1} msg${(s.turn_count || 1) === 1 ? '' : 's'}</span>
        </div>
        <div class="past-chat-preview">${escapeHtml(s.preview || (s.product ? 'Inquiry: ' + s.product : 'General conversation'))}</div>
        <div class="past-chat-actions">
          <button type="button" class="resume-chat-btn" data-sid="${s.session_id}">
            ${isCurrent ? 'Current Chat' : 'Resume This Chat 💬'}
          </button>
        </div>
      `;

      const btn = item.querySelector('.resume-chat-btn');
      if (!isCurrent) {
        btn.addEventListener('click', () => {
          resumePastChat(s.session_id);
        });
      } else {
        btn.disabled = true;
        btn.style.opacity = '0.6';
      }

      customerPastChatsList.appendChild(item);
    });
  }

  async function resumePastChat(targetSessionId) {
    try {
      const res = await fetch(`/api/customer/sessions/${encodeURIComponent(targetSessionId)}`);
      if (!res.ok) throw new Error('Could not load session details');
      const data = await res.json();
      const sess = data.session;
      if (!sess) return;

      sessionId = targetSessionId;
      sessionStorage.setItem('cra_session_id', sessionId);
      closeCustomerModal();

      // Clear container and replay history
      messagesContainer.innerHTML = '';
      clientLastMessageCount = 0;

      const history = sess.history || [];
      if (history.length === 0) {
        renderInitialGreeting();
      } else {
        history.forEach(turn => {
          const role = turn.role === 'user' ? 'user' : 'bot';
          const content = turn.content || '';
          if (role === 'user') {
            appendMessage('user', content);
          } else {
            appendMessage('bot', content, 'Previous Session', [], null, null, [], [], [], DEFAULT_AGENT);
          }
          clientLastMessageCount++;
        });
      }
    } catch (err) {
      console.error('Error resuming session:', err);
      alert('Could not resume selected session. Please try again.');
    }
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
      const r = Math.random() * 16 | 0;
      const v = c === 'x' ? r : (r & 0x3 | 0x8);
      return v.toString(16);
    });
  }
});


