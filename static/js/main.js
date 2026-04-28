document.addEventListener('DOMContentLoaded', function() {
    // Get user location
    function getLocation() {
        return new Promise((resolve, reject) => {
            if (!navigator.geolocation) {
                reject('Geolocation not supported');
            }
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    const lat = position.coords.latitude;
                    const lon = position.coords.longitude;
                    resolve({ lat, lon });
                },
                (error) => reject('Location access denied'),
                { timeout: 10000, enableHighAccuracy: true }
            );
        });
    }

    // Panic button handler
    const panicBtn = document.getElementById('panic-btn');
    const nameInput = document.getElementById('user-name');
    const locationInput = document.getElementById('location');
    const roomInput = document.getElementById('room-number');
    const typeInput = document.getElementById('emergency-type');

    if (panicBtn) {
        panicBtn.addEventListener('click', async function() {
            panicBtn.disabled = true;
            panicBtn.innerHTML = '<div class="loading"></div> Sending Alert...';

            try {
                const name = nameInput.value || 'Anonymous';
                const roomNumber = roomInput ? roomInput.value : 'Unknown';
                const emergencyType = typeInput ? typeInput.value : 'medical';
                let location = locationInput.value;

                if (!location) {
                    const coords = await getLocation();
                    location = `${coords.lat.toFixed(4)}, ${coords.lon.toFixed(4)}`;
                    locationInput.value = location;
                }

                const payload = {
                    name,
                    location,
                    room_number: roomNumber,
                    emergency_type: emergencyType
                };

                // Check if online
                if (!navigator.onLine) {
                    // Queue for offline sync
                    queueOfflineRequest('panic', payload);
                    showAlert('Offline: Alert queued. Will send when connection returns.', 'warning');
                    setTimeout(() => {
                        window.location.href = `/evacuation/${roomNumber || '101'}`;
                    }, 2000);
                    return;
                }

                const response = await fetch('/panic', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });

                const data = await response.json();

                if (response.ok) {
                    showAlert('Alert sent successfully! Help is on the way.', 'success');
                    setTimeout(() => {
                        window.location.href = `/status/${data.id}`;
                    }, 2000);
                } else {
                    throw new Error(data.error || 'Failed to send alert');
                }
            } catch (error) {
                showAlert('Error: ' + error.message, 'error');
                panicBtn.disabled = false;
                panicBtn.innerHTML = '<i class="fas fa-exclamation-triangle"></i><br>EMERGENCY SOS';
            }
        });
    }

    // Show alert messages
    function showAlert(message, type) {
        const alert = document.createElement('div');
        alert.className = `alert alert-${type}`;
        alert.style.cssText = 'padding: 1rem; border-radius: 10px; margin: 1rem 0; ' +
            (type === 'success' ? 'background: #d4edda; color: #155724;' :
             type === 'error' ? 'background: #f8d7da; color: #721c24;' :
             'background: #fff3cd; color: #856404;');
        alert.textContent = message;
        const container = document.querySelector('.container');
        if (container) {
            container.insertBefore(alert, container.children[1] || container.firstChild);
        }
        setTimeout(() => alert.remove(), 5000);
    }

    // Auto-detect location on page load
    if (locationInput) {
        locationInput.addEventListener('focus', async () => {
            if (!locationInput.value) {
                try {
                    const coords = await getLocation();
                    locationInput.value = `${coords.lat.toFixed(4)}, ${coords.lon.toFixed(4)}`;
                } catch (error) {
                    console.warn('Could not get location:', error);
                }
            }
        });
    }

    // Offline queue functions
    function queueOfflineRequest(action, payload) {
        const queue = JSON.parse(localStorage.getItem('offlineQueue') || '[]');
        queue.push({ action, payload, timestamp: new Date().toISOString() });
        localStorage.setItem('offlineQueue', JSON.stringify(queue));
    }

    // Sync offline queue when back online
    window.addEventListener('online', async () => {
        const queue = JSON.parse(localStorage.getItem('offlineQueue') || '[]');
        if (queue.length === 0) return;

        for (const item of queue) {
            try {
                await fetch('/api/offline-sync', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: item.action, payload: item.payload })
                });
            } catch (e) {
                console.error('Failed to sync:', e);
            }
        }

        // Clear queue after sync attempt
        localStorage.removeItem('offlineQueue');
        showAlert(`${queue.length} queued alerts synced!`, 'success');
    });
});
