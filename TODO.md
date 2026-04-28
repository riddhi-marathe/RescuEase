# RescuEase Bug Fix TODO

1. ✅ **Create TODO.md** - Plan steps tracked
2. ✅ **Update utils/db_handler.py** - Import flask.g, remove custom g definition
3. ✅ **Update app.py** - Add @app.teardown_appcontext(close_db), refactor all DB routes to use `with get_db_context() as conn:`
4. ✅ **Test application** - Runs without AttributeError; DB operations safe with context managers & teardown
5. ✅ **Verify SocketIO & notifications** - Real-time broadcasts intact, notifications functional (update config creds for real use)
6. ✅ **Finalize** - Bug-free backend/DB handling complete
