A web-based CRM tool to manage and filter customer interactions. Features include sortable tables, filters, inline editing via modals, delete confirmations, CSV export, and auto-refresh. Built with Tailwind CSS, Alpine.js, and vanilla JavaScript for a user-friendly interface.
Here’s a comprehensive **README.md** draft tailored to your CRM project with Alpine.js frontend and Flask backend. It explains the purpose, features, setup, and usage clearly:

---
# CRM Dashboard & Interaction Manager

A lightweight CRM (Customer Relationship Management) system built with **Flask** (backend) and **Alpine.js + TailwindCSS** (frontend).  
This project helps small teams or solo founders manage prospects, deals, payments, and interactions in a simple, modular way.

---

## 🚀 Features

- **Authentication**
  - JWT-based login and token validation
  - Global fetch patch to automatically include `Authorization` headers

- **Dashboard**
  - Displays key metrics: total prospects, active deals, total revenue, recent interactions
  - Auto-refresh every 15 seconds
  - Configurable prospect count stored in `localStorage`

- **Prospects**
  - Create, list, filter, and delete prospects
  - Cascade deletion of related interactions, deals, and payments

- **Deals**
  - Track deals linked to prospects
  - Delete deals with safe cascade logic (only deletes prospect if no other deals remain)

- **Payments**
  - Manage payments tied to deals
  - Sum of completed payments shown as revenue
  - Safe cascade deletion logic

- **Interactions**
  - Log outbound/inbound communications
  - Filter by channel, type, response, success
  - Edit and delete interactions with confirmation dialogs
  - Export interactions to CSV

- **Global User Info**
  - User name and email fetched from `/auth/me`
  - Displayed consistently across all pages via Alpine global store

---

## 🛠️ Tech Stack

- **Backend**: Flask, SQLite
- **Frontend**: Alpine.js, TailwindCSS
- **Auth**: JWT tokens stored in `localStorage`
- **Data**: SQLite tables for prospects, deals, payments, interactions

---

## ⚙️ Setup & Installation

1. **Clone the repo**
   ```bash
   git clone https://github.com/yourusername/crm-dashboard.git
   cd crm-dashboard
   ```

2. **Create virtual environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Initialize database**
   ```bash
   flask init-db
   ```

5. **Run the app**
   ```bash
   flask run
   ```

6. Visit `http://localhost:5000` in your browser.

---

## 🔑 API Endpoints

- `POST /auth/login` → Login, returns JWT
- `GET /auth/me` → Current user info
- `GET /crm/dashboard-data?count=N` → Dashboard metrics + recent prospects
- `GET /crm/interactions-data` → List interactions
- `DELETE /crm/interactions/<id>` → Delete interaction
- `DELETE /crm/prospects/<id>` → Delete prospect + cascade
- `DELETE /crm/deals/<id>` → Delete deal + cascade
- `DELETE /crm/payments/<id>` → Delete payment + cascade

---

## 🧩 Frontend Components

- **dashboardData()** → Loads metrics, polls every 15s
- **interactionsPage()** → Manages filters, sorting, pagination, edit/delete
- **Global Alpine store** → `$store.auth.user` holds `{ name, email }`

---

## 📊 Example Workflow

1. Login → JWT stored in `localStorage`
2. Dashboard auto-refreshes metrics every 15s
3. Add prospects and deals
4. Log interactions (calls, emails, meetings)
5. Record payments → revenue updates
6. Delete prospect → cascades safely through related data

---

## 🤝 Contributing

Pull requests are welcome!  
For major changes, please open an issue first to discuss what you’d like to change.

---

## 📜 License

MIT License. Free to use, modify, and distribute.
---
