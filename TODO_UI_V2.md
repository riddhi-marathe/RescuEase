# RescuEase UI v2 — Global Professional Update

## Requirements
1. Update staff login page
2. Change background of ALL pages to professional
3. Remove cards, use only few cards
4. Update analytics graph to use pie chart
5. Add animation in home/landing page

---

## Plan

### 1. Global Background & Base Styles (`static/css/style.css`)
- Change `body` background from purple gradient to professional dark navy `#0f172a` with subtle geometric dot pattern
- Update `.card` to be flatter, fewer shadows, used sparingly
- Add `.page-bg` helper class for consistent page backgrounds
- Reduce default `.card` padding and shadow to make cards less prominent

### 2. Staff Login Page (`templates/login.html`)
- Replace hero + card layout with clean centered login (no card wrapper)
- Use subtle glassmorphism panel instead of heavy card
- Add animated floating shapes in background
- Keep form simple: username, password, login button

### 3. Landing / Home Page Animations (`templates/landing.html`)
- Add floating animated orbs/particles in background
- Add fade-in-up animations for role cards on load
- Add hover scale animation on role cards
- Keep existing loading screen and drift animation

### 4. Incident Log / Analytics (`templates/incident_log.html`)
- Consolidate all analytics into ONE card container
- Replace multiple stat cards with a clean stat row (no card backgrounds)
- Change Chart.js from `doughnut` to `pie` with professional colors
- Reduce card usage: 1 main card for charts, 1 for table, filters inline

### 5. Resources Page (`templates/resources.html`)
- Replace per-resource cards with clean table/list layout
- Keep only 1 header card or remove it entirely
- Status shown as colored dots/badges, not full card backgrounds

### 6. Contacts Page (`templates/contacts.html`)
- Replace per-contact cards with compact contact list rows
- Keep only 1 page header (no card)
- One-click call as a button, not a full card

### 7. Staff Profile (`templates/staff_profile.html`)
- Consolidate profile info + stats into single clean layout (no cards)
- Assigned emergencies as a compact list, not cards

### 8. Guest Dashboard (`templates/guest_dashboard.html`)
- Reduce quick-action cards to icon buttons or a single action bar
- My emergencies as a list, not cards

### 9. Admin Approvals (`templates/admin_approvals.html`)
- Stats bar without card backgrounds
- Approval list as clean rows, not cards

### 10. SOS Page (`templates/index.html`)
- Remove feature cards at bottom
- Keep panic button prominent with minimal surrounding UI

---

## Files to Edit
1. `static/css/style.css` — Global background, reduced card styles, new utilities
2. `templates/login.html` — New login design
3. `templates/landing.html` — Animations
4. `templates/incident_log.html` — Pie chart, fewer cards
5. `templates/resources.html` — Table/list instead of cards
6. `templates/contacts.html` — List instead of cards
7. `templates/staff_profile.html` — Consolidated layout
8. `templates/guest_dashboard.html` — Fewer cards
9. `templates/admin_approvals.html` — Fewer cards
10. `templates/index.html` — Remove feature cards

## Follow-up
- Restart server and test each page
- Verify responsive behavior

