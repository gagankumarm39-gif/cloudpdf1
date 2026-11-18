# User Guide: Cloud-Based PDF Generation System

## Milestone 12 User Manual

Welcome to **CloudPDF Studio** — an end-to-end cloud-native document creation, compilation, and storage platform. This manual walks you through using every feature of the application.

---

## 1. Getting Started & Account Registration

### 1.1 Registering an Account
1. Open the application in your browser (e.g. `http://127.0.0.1:5000` or your Render deployment URL).
2. If you are not signed in, you will be directed to the **Sign In** screen.
3. Click **Create an account** or navigate to `/register`.
4. Enter your:
   - **Full Name**
   - **Email Address** (must be a valid email format)
   - **Password** (minimum 8 characters, containing at least one letter and one number)
   - **Confirm Password**
5. Click **Create Account**. You will be registered and automatically logged in to your private dashboard.

### 1.2 Logging In & Out
- **Login**: Navigate to `/login`, enter your email and password, and click **Sign In**.
- **Logout**: Click the **Sign Out** button in the navigation bar to end your session securely.

---

## 2. Generating Publication-Quality PDFs

1. In the **PDF Document Studio** pane on the left:
2. **Document Title**: Enter a descriptive title (e.g., `Cloud Computing Semester Report`).
3. **Author Name**: Enter your name or team name (defaults to your registered account name).
4. **Description / Abstract**: Provide a brief executive summary.
5. **Main Document Content**: Type or paste your document text.
   - Use paragraph line breaks to format multi-paragraph sections.
   - The ReportLab engine will automatically compute flowables, running headers, table cards, and two-pass page counts ("Page X of Y").
6. Choose your delivery mode:
   - **Generate & Download**: Compiles the document, archives it to Supabase Storage, indexes it in PostgreSQL, and immediately initiates a browser download of the `.pdf` file.
   - **Generate in Cloud (JSON)**: Saves the document directly to your cloud catalog without initiating an immediate file download.

---

## 3. Managing Your Document Catalog

### 3.1 Viewing Document History
The **Generated Documents** table on the right displays all documents you have generated:
- **Title & Description**: Document metadata and abstract.
- **Author & Date**: Stated author and exact UTC generation timestamp.
- **File Size**: Human-readable file size (e.g., `214.2 KB`).
- **Cloud Status**: Indicates whether the binary is securely synchronized with Supabase Storage.

### 3.2 Searching and Filtering Documents
- Use the **Search documents...** input box above the table.
- Type any keyword matching the **Title**, **Author**, or **Document ID** (`DOC-XXXX`).
- The catalog filters dynamically without requiring a page refresh.

### 3.3 Sorting Documents
Use the sort dropdown to order your documents by:
- **Newest First (Default)**
- **Oldest First**
- **Title (A–Z)**
- **File Size (Largest First)**

---

## 4. Previewing and Downloading PDFs

### 4.1 In-Browser PDF Preview
1. In the document row, click the **Preview** button (eye icon).
2. A modal dialog will appear with an embedded PDF viewer.
3. Because the storage bucket is private, the backend generates an ephemeral signed URL that expires in 1 hour.
4. You can read, zoom, print, or review the document directly within the browser without downloading it to your disk.
5. Click the close button (`×`) or click outside the modal to exit.

### 4.2 Downloading Stored PDFs
1. In the document row, click the **Download** button (down-arrow icon).
2. The server streams the PDF attachment with a clean, safe filename.

---

## 5. Deleting Documents

1. In the document row, click the **Delete** button (trash-can icon).
2. A confirmation prompt will ask: *"Are you sure you want to delete this document?"*.
3. Click **OK** to confirm.
4. The file is deleted from Supabase Storage and its metadata is removed from Supabase PostgreSQL.
5. The document history table and dashboard metrics update immediately.

---

## 6. Dashboard Metrics & Analytics

The top metric cards update in real time:
- **Total Generated**: Total count of active documents owned by your account.
- **Cloud Storage Consumed**: Aggregate disk storage consumed in bytes, KB, or MB.
- **Cloud Storage Status**: Live connectivity status of Supabase Storage (`pdf-documents`).
- **Database Status**: Live status of Supabase PostgreSQL.
