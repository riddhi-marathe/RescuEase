document.addEventListener('DOMContentLoaded', function() {
    const socket = io();
    
    socket.on('connect', function() {
        console.log('Connected to RescuEase real-time server');
    });

    // New emergency alert
    socket.on('new_emergency', function(data) {
        showNotification(`🚨 New Emergency #${data.id}: ${data.name} - ${data.emergency_type || 'medical'}`, 'error');
        
        // If on dashboard, prepend new card
        const container = document.getElementById('emergencies-container');
        if (container) {
            const card = createEmergencyCard(data);
            container.insertBefore(card, container.firstChild);
        }
    });

    // Status update
    socket.on('status_update', function(data) {
        showNotification(`📊 Emergency #${data.id} updated to ${data.status}`, 'success');
        
        // Update card status on dashboard
        const card = document.querySelector(`.emergency-card[data-emergency-id="${data.id}"]`);
        if (card) {
            card.className = `emergency-card ${data.status}`;
            const badge = card.querySelector('.status-badge');
            if (badge) badge.textContent = data.status.toUpperCase();
        }
        
        // Update progress bar on track page
        const progressFill = document.getElementById('progress-fill');
        if (progressFill) {
            progressFill.style.width = data.status === 'pending' ? '33%' : 
                                       data.status === 'in-progress' ? '66%' : '100%';
        }
    });

    // Track update with history
    socket.on('track_update', function(data) {
        if (data.history) {
            updateTimeline(data.history);
        }
    });

    // Escalation alert
    socket.on('escalation_alert', function(data) {
        showNotification(`⚠️ ${data.message}`, 'warning');
    });

    // Acknowledgment
    socket.on('acknowledged', function(data) {
        showNotification(`✅ Emergency #${data.id} acknowledged by ${data.staff}`, 'success');
    });

    // Helper functions
    function showNotification(message, type) {
        // Remove existing notifications
        const existing = document.querySelector('.toast-notification');
        if (existing) existing.remove();
        
        const toast = document.createElement('div');
        toast.className = 'toast-notification';
        toast.style.cssText = `
            position: fixed;
            top: 100px;
            right: 20px;
            background: ${type === 'error' ? '#ff6b6b' : type === 'warning' ? '#ffa502' : '#2ed573'};
            color: white;
            padding: 1rem 2rem;
            border-radius: 10px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
            z-index: 10000;
            animation: slideInRight 0.3s ease;
            max-width: 350px;
            font-weight: 600;
        `;
        toast.innerHTML = `<i class="fas fa-${type === 'error' ? 'exclamation-circle' : type === 'warning' ? 'exclamation-triangle' : 'check-circle'}"></i> ${message}`;
        document.body.appendChild(toast);
        setTimeout(() => toast.remove(), 5000);
    }

    function createEmergencyCard(data) {
        const div = document.createElement('div');
        div.className = `emergency-card ${data.status}`;
        div.setAttribute('data-emergency-id', data.id);
        div.innerHTML = `
            <div class="status-badge">${data.status.toUpperCase()}</div>
            <h3>#${data.id} - ${data.name}</h3>
            <p><strong>Type:</strong> <span class="type-badge">${(data.emergency_type || 'MEDICAL').toUpperCase()}</span></p>
            <p><strong>Location:</strong> ${data.location}</p>
            <p><strong>Room:</strong> ${data.room_number || 'N/A'}</p>
            <div class="action-buttons">
                <a href="/evacuation/${data.room_number || '101'}" class="btn" style="background: #ff6b6b; color: white;"><i class="fas fa-running"></i> Evacuate</a>
                <a href="/track/${data.id}" class="btn btn-primary"><i class="fas fa-map-marker-alt"></i> Track</a>
            </div>
        `;
        return div;
    }

    // Timeline update function (global for track page)
    window.updateTimeline = function(history) {
        const container = document.getElementById('timeline-items');
        if (!container) return;
        
        container.innerHTML = '';
        history.forEach((event, index) => {
            const item = document.createElement('div');
            item.className = 'timeline-item';
            item.innerHTML = `
                <div class="timeline-dot" style="background: ${event.status === 'resolved' ? '#2ed573' : event.status === 'in-progress' ? '#ffa502' : '#ff6b6b'};"></div>
                <div class="timeline-content">
                    <div class="timeline-time">${new Date(event.timestamp).toLocaleString()}</div>
                    <div class="timeline-status">${event.status.toUpperCase()}</div>
                    <p>${event.note || 'Status updated'}</p>
                    <small>By: ${event.updated_by || 'System'}</small>
                </div>
            `;
            container.appendChild(item);
        });
    };

    // Dark mode toggle
    const darkToggle = document.getElementById('dark-toggle');
    if (darkToggle) {
        darkToggle.addEventListener('click', () => {
            document.body.classList.toggle('dark-mode');
            const icon = darkToggle.querySelector('i');
            icon.className = document.body.classList.contains('dark-mode') ? 'fas fa-sun' : 'fas fa-moon';
        });
    }

    // Add timeline event (for track page)
    window.addTimelineEvent = function(status) {
        const note = document.getElementById('status-note')?.value || '';
        fetch(`/update_status/${window.emergencyId}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({status: status, note: note})
        })
        .then(r => r.json())
        .then(data => {
            showNotification(data.message, 'success');
            if (status === 'resolved') {
                setTimeout(() => location.reload(), 1000);
            }
        });
    };
});
