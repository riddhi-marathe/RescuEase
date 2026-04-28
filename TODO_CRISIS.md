# Full-Scale Crisis Management Suite TODO

## Phase 1: Database Schema Expansion
- [ ] Add rooms, exits tables for evacuation routing
- [ ] Add resources table (first-aid, extinguishers)
- [ ] Add contacts table (hospitals, police, fire)
- [ ] Add escalation_levels table
- [ ] Add offline_queue table
- [ ] Add analytics_logs table

## Phase 2: New Templates
- [ ] templates/evacuation.html - Evacuation Map with path to exit
- [ ] templates/incident_log.html - Analytics & history
- [ ] templates/resources.html - Resource management dashboard
- [ ] templates/contacts.html - Emergency contacts with one-click call
- [ ] templates/staff_profile.html - Staff profile & login details
- [ ] templates/priority_escalation.html - Escalation monitoring

## Phase 3: Backend Routes & Logic
- [ ] /evacuation/<room_id> - Evacuation routing
- [ ] /incident-log - Analytics dashboard
- [ ] /resources - Resource management
- [ ] /contacts - Emergency contacts
- [ ] /staff/profile - User profile
- [ ] /api/escalate - Priority escalation API
- [ ] /api/offline-sync - Offline queue sync
- [ ] AI threat detection integration (mock/simulation)

## Phase 4: Enhanced Features
- [ ] Realistic Leaflet.js maps integration
- [ ] WhatsApp integration (Twilio)
- [ ] Priority escalation timer (30s auto-escalate)
- [ ] PWA offline support (service worker)
- [ ] Response time analytics charts

## Phase 5: Connect Everything
- [ ] Update navigation across all pages
- [ ] Unified socket events
- [ ] Cross-page state management

