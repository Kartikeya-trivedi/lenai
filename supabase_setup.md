# Supabase Setup Guide

To deploy LenAI to the cloud using Modal, you need a highly available, managed PostgreSQL database. **Supabase** is perfect for this.

## 1. Create a Supabase Project
1. Go to [database.new](https://database.new/) and sign in.
2. Create a new project. Choose a secure database password and save it.
3. Wait 1-2 minutes for the database to provision.

## 2. Get the Connection String
Because serverless functions (like Modal or AWS Lambda) scale up and down rapidly, they can exhaust standard database connections. You **must** use the Supabase Transaction Pooler.

1. In your Supabase dashboard, go to **Project Settings** -> **Database**.
2. Scroll down to **Connection pooling**.
3. Copy the Connection pooler string (it will look like `postgresql://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres`).
4. Ensure the port is `6543` (transaction mode) and that you've replaced `[password]` with your actual password.
5. Note: Since our backend uses SQLAlchemy `asyncpg`, replace `postgresql://` with `postgresql+asyncpg://` in the URL!

## 3. Set up the Modal Secret
Modal needs secure access to this connection string so your API can talk to the database.

1. Go to your [Modal Dashboard Secrets page](https://modal.com/secrets).
2. Click **Create Secret** -> **Custom**.
3. Name the secret: `lenai-db-secret`
4. Add a key called `DATABASE_URL` and paste your async Supabase connection pooler string as the value.
5. Click **Create**.

## 4. Deploy!
You are now ready to deploy the platform to Modal. Run:
```bash
modal deploy modal_app.py
```
