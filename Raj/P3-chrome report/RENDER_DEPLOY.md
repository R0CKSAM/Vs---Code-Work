# Render Deployment

This project is now prepared for deployment on Render.

## What is already added

- `gunicorn` in `requirements.txt`
- `render.yaml` for Render web service setup
- `.python-version` to pin Python
- Flask app updated to support Render's `PORT`

## Before deploying

1. Put this project in a GitHub repository.
2. Make sure your `data/` folder contains the Excel files you want available online.
3. Push the latest code to GitHub.

## Deploy on Render

1. Sign in to Render.
2. Click `New` -> `Blueprint`.
3. Connect your GitHub repository.
4. Render will detect `render.yaml`.
5. Create the service.

Render will use:

- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app`

## Result

After the first successful deploy, Render will give you a public URL like:

`https://chrome-report-dashboard.onrender.com`

Anyone with that URL can open the dashboard.

## Important note

If you update Excel files later, you must:

1. add/replace them in the repo
2. push to GitHub again
3. let Render redeploy

## Free plan note

Render's free web services can sleep after inactivity, so the first open after idle time may take a little longer.
