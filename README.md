# TDS GA0 — Code Interpreter with AI Error Analysis

## Files
- `main.py`: FastAPI implementation with `POST /code-interpreter`, CORS, exact stdout/traceback response, and Gemini structured error-line analysis.
- `requirements.txt`: dependencies for deployment.

## Deploy on Render
1. Upload both files to a GitHub repository.
2. In Render, create a **Web Service** connected to that repository.
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Add environment variable `GEMINI_API_KEY` with your Google AI Studio API key. Optionally set `GEMINI_MODEL`; default is `gemini-3.5-flash-lite`.
6. Deploy and wait for the service to report **Live**.
7. Check `https://YOUR-SERVICE.onrender.com/health` returns `{"status":"ok"}`.
8. In the assignment, enter `https://YOUR-SERVICE.onrender.com/code-interpreter`.

## Test
Open `https://YOUR-SERVICE.onrender.com/docs`, expand `POST /code-interpreter`, and use one of these JSON bodies:

Success:
```json
{"code":"x = 5\ny = 10\nprint(x + y)"}
```
Expected response has `error: []` and `result: "15\n"`.

Error on line 3:
```json
{"code":"x = 10\ny = 0\nresult = x / y"}
```
Expected response has `error: [3]` and a traceback in `result`.

## Security warning
This is a temporary classroom demo for the assignment. Executing arbitrary Python code on a public endpoint is dangerous, even with a timeout and a child process. Do not use it for production or place other sensitive credentials/files on the same service. After the assignment accepts the URL, disable or delete the service and revoke/rotate the API key if you no longer need it.
