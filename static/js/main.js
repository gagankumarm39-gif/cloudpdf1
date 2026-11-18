/**
 * CloudPDF Studio - Client Application Logic
 * Milestone 1 - Project Foundation and UI
 */

document.addEventListener("DOMContentLoaded", () => {
    // Character counter for the textarea
    const contentTextarea = document.getElementById("docContent");
    const charCounter = document.getElementById("charCount");

    if (contentTextarea && charCounter) {
        contentTextarea.addEventListener("input", (e) => {
            const count = e.target.value.length;
            charCounter.textContent = `${count.toLocaleString()} characters`;
        });
    }

    // Auto-smooth scroll setup for any internal anchors
    document.querySelectorAll("a[href^=\"#\"]").forEach(anchor => {
        anchor.addEventListener("click", function (e) {
            const targetId = this.getAttribute("href");
            if (targetId && targetId !== "#") {
                const targetEl = document.querySelector(targetId);
                if (targetEl) {
                    e.preventDefault();
                    targetEl.scrollIntoView({ behavior: "smooth" });
                }
            }
        });
    });
});

// Pre-defined Templates Data
const TEMPLATES = {
    academic: {
        title: "Cloud Computing Lab Project Report - Cloud-Based PDF Engine",
        author: "Kavya M",
        description: "Semester project documentation covering AWS cloud architecture, ReportLab pipeline, and S3 storage specifications.",
        content: `1. PROJECT OVERVIEW
The Cloud-Based PDF Generation System delivers automated server-side PDF document compilation with elastic AWS cloud storage and metadata indexing.

2. SYSTEM ARCHITECTURE
- Presentation Layer: HTML5, CSS3, JavaScript responsive UI.
- Processing Layer: Python Flask application hosted on Amazon EC2.
- Rendering Engine: ReportLab library for programmatic vector document generation.
- Persistence Layer: Amazon Simple Storage Service (S3) for storage & Amazon DynamoDB for document metadata indexing.

3. EVALUATION CRITERIA
- Generation latency: < 800ms
- Storage redundancy: 99.999999999% (11 9s) S3 durability
- Security: Role-based IAM policies with restricted bucket policies.`
    },
    technical: {
        title: "AWS Multi-Tier Architecture & Infrastructure Specification",
        author: "Cloud Infrastructure Team",
        description: "Technical specification for AWS cloud resources, VPC, subnets, and IAM roles for the PDF generator.",
        content: `AWS ARCHITECTURE SPECIFICATION

1. COMPUTE (Amazon EC2)
- Instance Type: t3.micro / t3.small for student tier.
- OS: Amazon Linux 2023 or Ubuntu 22.04 LTS.
- Security Group: Port 80/443 (HTTP/HTTPS) and Port 22 (SSH restricted).

2. STORAGE (Amazon S3)
- Bucket Name: cloud-pdf-storage-vault
- Encryption: SSE-S3 (Server-Side Encryption with Amazon S3 managed keys)
- Lifecycle: Auto-archive to S3 Glacier after 90 days.

3. METADATA (Amazon DynamoDB)
- Table Name: DocumentsMetadata
- Primary Partition Key: DocumentId (String)
- Global Secondary Index: AuthorIndex (Partition Key: Author, Sort Key: CreatedAt)`
    },
    business: {
        title: "Cloud Document Automation - Executive Summary",
        author: "Project Advisory Board",
        description: "Executive brief highlighting the cloud business benefits of centralized PDF rendering.",
        content: `EXECUTIVE SUMMARY: CLOUD PDF PLATFORM

1. OBJECTIVE
To eliminate local dependency for document generation by centralizing document authoring, formatting, and long-term cloud archiving into a high-availability cloud portal.

2. VALUE PROPOSITION
- Anywhere Access: Users can create and download generated reports anywhere over HTTPS.
- Zero Installation: No client-side PDF printer or rendering drivers required.
- Cost Efficiency: Leverages AWS Free Tier compatible components for student and startup budgets.`
    }
};

/**
 * Auto-populates the studio form with template contents
 * @param {string} type - 'academic' | 'technical' | 'business'
 */
function loadTemplate(type) {
    const data = TEMPLATES[type];
    if (!data) return;

    document.getElementById("docTitle").value = data.title;
    document.getElementById("authorName").value = data.author;
    document.getElementById("docDescription").value = data.description;
    
    const contentEl = document.getElementById("docContent");
    contentEl.value = data.content;

    // Trigger char count update
    const charCounter = document.getElementById("charCount");
    if (charCounter) {
        charCounter.textContent = `${data.content.length.toLocaleString()} characters`;
    }

    // Smooth scroll down to creation section
    const createSection = document.getElementById("create-section");
    if (createSection) {
        createSection.scrollIntoView({ behavior: "smooth" });
    }

    // Highlight notification
    showStatusNotification(
        "Template Applied",
        `Loaded "${data.title.substring(0, 35)}..." into the studio form.`,
        "success"
    );
}

/**
 * Resets the document generation form
 */
function resetForm() {
    const form = document.getElementById("pdfGenerationForm");
    if (form) {
        form.reset();
        const charCounter = document.getElementById("charCount");
        if (charCounter) charCounter.textContent = "0 characters";
        hideStatusNotification();
    }
}

/**
 * Handles Form Submission in Milestone 1
 * Demonstrates local validation, responsive UI feedback, and adds the doc to the recent table.
 */
/**
 * Handles Form Submission in Milestone 2
 * Validates fields, calls POST /api/generate-pdf, displays loading,
 * automatically downloads the rendered PDF, and updates the UI table.
 */
/**
 * Milestone 3: Client Application State & Modal Controls
 */
let currentPreviewDocId = null;
let currentPreviewDocTitle = "";
let pendingDeleteDocId = null;
let searchDebounceTimer = null;

/**
 * Handles Form Submission in Milestone 2 & 3
 * Validates fields, calls POST /api/generate-pdf, displays loading,
 * automatically downloads the rendered PDF, and refreshes the document catalog.
 */
async function handleGeneratePDF(event) {
    event.preventDefault();

    const title = document.getElementById("docTitle").value.trim();
    const author = document.getElementById("authorName").value.trim();
    const description = document.getElementById("docDescription").value.trim();
    const content = document.getElementById("docContent").value.trim();

    if (!title || !author || !content) {
        showStatusNotification(
            "Validation Error",
            "Please fill in all required fields (Document Title, Author Name, Main Content).",
            "error"
        );
        return;
    }

    const submitBtn = document.getElementById("submitBtn");
    const originalBtnHtml = submitBtn.innerHTML;

    // Loading State
    submitBtn.disabled = true;
    submitBtn.innerHTML = "<i class=\"fa-solid fa-spinner fa-spin\"></i> Compiling PDF Engine...";

    showStatusNotification(
        "Rendering PDF Document",
        "ReportLab flowable engine is calculating typography, margins, and page layouts...",
        "loading"
    );

    try {
        const response = await fetch("/api/generate-pdf?download=true", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                title: title,
                author: author,
                description: description,
                content: content
            })
        });

        if (!response.ok) {
            let errorMsg = `Server error (${response.status})`;
            try {
                const errData = await response.json();
                errorMsg = errData.error || errData.message || errorMsg;
            } catch (_) {}
            throw new Error(errorMsg);
        }

        // Extract metadata passed via response headers
        const docId = response.headers.get("X-Doc-Id") || `DOC-${Math.floor(1000 + Math.random() * 9000)}`;
        const docSize = response.headers.get("X-Doc-Size") || "120 KB";
        const filename = response.headers.get("X-Doc-Filename") || `${docId}_document.pdf`;

        // Receive the binary PDF blob
        const blob = await response.blob();
        const downloadUrl = window.URL.createObjectURL(blob);

        // Auto-trigger browser download
        const a = document.createElement("a");
        a.href = downloadUrl;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => window.URL.revokeObjectURL(downloadUrl), 5000);

        // Refresh documents table from repository to sync search, sort & stats
        await fetchDocuments();

        showStatusNotification(
            "PDF Generated & Downloaded Successfully!",
            `"${title}" (ID: ${docId}) compiled via ReportLab and saved. You can also preview it from Document History.`,
            "success"
        );

    } catch (err) {
        console.error("PDF generation error:", err);
        showStatusNotification(
            "PDF Generation Failed",
            err.message || "An unexpected error occurred while compiling the document.",
            "error"
        );
    } finally {
        submitBtn.disabled = false;
        submitBtn.innerHTML = originalBtnHtml;
    }
}

/**
 * Fetches documents from the backend with current search & sort filters
 */
async function fetchDocuments() {
    const searchInput = document.getElementById("docSearchInput");
    const sortSelect = document.getElementById("docSortSelect");

    const query = searchInput ? searchInput.value.trim() : "";
    let sortField = "date";
    let sortOrder = "desc";

    if (sortSelect) {
        const [field, order] = sortSelect.value.split("-");
        sortField = field || "date";
        sortOrder = order || "desc";
    }

    const params = new URLSearchParams({
        search: query,
        sort: sortField,
        order: sortOrder
    });

    try {
        const response = await fetch(`/api/documents?${params.toString()}`);
        if (!response.ok) throw new Error("Failed to load documents.");
        const data = await response.json();

        renderDocumentsTable(data.documents || []);

        // Update badge count
        const badge = document.getElementById("docCountBadge");
        if (badge) {
            badge.textContent = `${(data.documents || []).length} items`;
        }

        // Update dashboard statistics
        if (data.statistics) {
            updateDashboardMetrics(data.statistics);
        }
    } catch (err) {
        console.error("Error fetching documents:", err);
    }
}

/**
 * Renders document rows into the table
 */
function renderDocumentsTable(documents) {
    const tableBody = document.querySelector("#documentsTable tbody");
    const emptyState = document.getElementById("tableEmptyState");
    const emptyMsg = document.getElementById("emptyStateMsg");
    if (!tableBody) return;

    tableBody.innerHTML = "";

    if (!documents || documents.length === 0) {
        if (emptyState) emptyState.classList.remove("d-none");
        const searchInput = document.getElementById("docSearchInput");
        if (emptyMsg) {
            if (searchInput && searchInput.value.trim()) {
                emptyMsg.textContent = `No documents found matching "${searchInput.value.trim()}".`;
            } else {
                emptyMsg.textContent = "Your document history is currently empty. Generate a PDF to begin.";
            }
        }
        return;
    }

    if (emptyState) emptyState.classList.add("d-none");

    documents.forEach(doc => {
        const tr = document.createElement("tr");
        tr.id = `row-${doc.id}`;
        tr.innerHTML = `
            <td><span class="doc-code">${escapeHtml(doc.id)}</span></td>
            <td class="font-medium">${escapeHtml(doc.title)}</td>
            <td>${escapeHtml(doc.author)}</td>
            <td class="text-muted">${escapeHtml(doc.created_at)}</td>
            <td>${escapeHtml(doc.size)}</td>
            <td>
                <span class="status-pill status-ready">
                    <i class="fa-solid fa-check"></i> ${escapeHtml(doc.status)}
                </span>
            </td>
            <td>
                <div class="table-actions">
                    <button class="action-btn btn-action-preview" title="Preview PDF in Browser" onclick="openPdfPreview('${escapeHtml(doc.id)}', '${escapeHtml(doc.title)}')">
                        <i class="fa-solid fa-eye"></i>
                    </button>
                    <button class="action-btn btn-action-download" title="Download Document" onclick="triggerDownloadById('${escapeHtml(doc.id)}')">
                        <i class="fa-solid fa-download"></i>
                    </button>
                    <button class="action-btn btn-action-delete" title="Delete Document" onclick="promptDeleteDocument('${escapeHtml(doc.id)}', '${escapeHtml(doc.title)}')">
                        <i class="fa-solid fa-trash-can"></i>
                    </button>
                </div>
            </td>
        `;
        tableBody.appendChild(tr);
    });
}

/**
 * Updates hero and dashboard metrics
 */
function updateDashboardMetrics(stats) {
    const totalEl = document.getElementById("totalGeneratedVal");
    if (totalEl && stats.total_generated !== undefined) {
        totalEl.textContent = stats.total_generated;
    }
}

/**
 * Search Debounce Handler
 */
function debounceSearch() {
    const clearBtn = document.getElementById("clearSearchBtn");
    const input = document.getElementById("docSearchInput");
    if (clearBtn && input) {
        if (input.value.trim().length > 0) {
            clearBtn.classList.remove("d-none");
        } else {
            clearBtn.classList.add("d-none");
        }
    }

    clearTimeout(searchDebounceTimer);
    searchDebounceTimer = setTimeout(() => {
        fetchDocuments();
    }, 250);
}

/**
 * Clears search input and reloads documents
 */
function clearSearch() {
    const input = document.getElementById("docSearchInput");
    const clearBtn = document.getElementById("clearSearchBtn");
    if (input) input.value = "";
    if (clearBtn) clearBtn.classList.add("d-none");
    fetchDocuments();
}

/**
 * Sorting Change Handler
 */
function applySorting() {
    fetchDocuments();
}

/**
 * ----------------------------------------------------
 * PDF Preview Modal Logic
 * ----------------------------------------------------
 */
function openPdfPreview(docId, docTitle) {
    currentPreviewDocId = docId;
    currentPreviewDocTitle = docTitle;

    const modal = document.getElementById("pdfPreviewModal");
    const titleEl = document.getElementById("previewModalTitle");
    const docIdEl = document.getElementById("previewModalDocId");
    const iframe = document.getElementById("pdfPreviewFrame");
    const spinner = document.getElementById("previewLoadingSpinner");

    if (!modal || !iframe) return;

    if (titleEl) titleEl.textContent = docTitle || "Document Preview";
    if (docIdEl) docIdEl.textContent = docId;

    // Show spinner & hide iframe while loading
    if (spinner) spinner.classList.remove("d-none");
    iframe.classList.add("d-none");

    // Point iframe to dedicated inline preview endpoint
    iframe.src = `/api/documents/${encodeURIComponent(docId)}/preview`;

    modal.classList.remove("d-none");
    document.body.style.overflow = "hidden"; // Prevent background scroll
}

function handlePdfIframeLoaded() {
    const iframe = document.getElementById("pdfPreviewFrame");
    const spinner = document.getElementById("previewLoadingSpinner");
    if (spinner) spinner.classList.add("d-none");
    if (iframe) iframe.classList.remove("d-none");
}

function closePdfPreview() {
    const modal = document.getElementById("pdfPreviewModal");
    const iframe = document.getElementById("pdfPreviewFrame");
    if (iframe) iframe.src = "";
    if (modal) modal.classList.add("d-none");
    document.body.style.overflow = "";
    currentPreviewDocId = null;
}

function handleModalBackdropClick(event) {
    if (event.target.id === "pdfPreviewModal") {
        closePdfPreview();
    }
}

function downloadCurrentPreview() {
    if (currentPreviewDocId) {
        triggerDownloadById(currentPreviewDocId);
    }
}

/**
 * ----------------------------------------------------
 * Document Download Handler
 * ----------------------------------------------------
 */
function triggerDownloadById(docId) {
    if (!docId) return;
    window.location.href = `/api/documents/${encodeURIComponent(docId)}/download`;
}

/**
 * ----------------------------------------------------
 * Document Delete Modal Logic
 * ----------------------------------------------------
 */
function promptDeleteDocument(docId, docTitle) {
    pendingDeleteDocId = docId;
    const modal = document.getElementById("deleteConfirmModal");
    const titleEl = document.getElementById("deleteTargetTitle");
    const idEl = document.getElementById("deleteTargetId");

    if (titleEl) titleEl.textContent = docTitle;
    if (idEl) idEl.textContent = docId;

    if (modal) modal.classList.remove("d-none");
    document.body.style.overflow = "hidden";
}

function closeDeleteModal() {
    const modal = document.getElementById("deleteConfirmModal");
    if (modal) modal.classList.add("d-none");
    document.body.style.overflow = "";
    pendingDeleteDocId = null;
}

function handleDeleteBackdropClick(event) {
    if (event.target.id === "deleteConfirmModal") {
        closeDeleteModal();
    }
}

async function confirmDeleteDocument() {
    if (!pendingDeleteDocId) return;

    const docId = pendingDeleteDocId;
    const btn = document.getElementById("confirmDeleteBtn");
    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = "<i class=\"fa-solid fa-spinner fa-spin\"></i> Deleting...";

    try {
        const response = await fetch(`/api/documents/${encodeURIComponent(docId)}`, {
            method: "DELETE"
        });

        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.error || "Failed to delete document.");
        }

        closeDeleteModal();
        await fetchDocuments();

        showStatusNotification(
            "Document Deleted",
            `Document "${docId}" has been deleted from local storage and repository.`,
            "success"
        );
    } catch (err) {
        alert(`Failed to delete document: ${err.message}`);
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalText;
    }
}

/**
 * Tests the /api/health endpoint and updates the health status box
 */
async function checkApiHealth() {
    const resultBox = document.getElementById("apiHealthResult");
    if (!resultBox) return;

    resultBox.textContent = "Pinging /api/health...";

    try {
        const response = await fetch("/api/health");
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        resultBox.textContent = JSON.stringify(data, null, 2);
    } catch (err) {
        resultBox.textContent = `Health check failed: ${err.message}`;
    }
}

/**
 * Shows the status banner with custom message
 * @param {string} heading
 * @param {string} message
 * @param {string} state - 'success' | 'loading' | 'error'
 */
function showStatusNotification(heading, message, state = "success") {
    const banner = document.getElementById("statusNotification");
    const spinner = document.getElementById("statusSpinner");
    const successIcon = document.getElementById("statusSuccessIcon");
    const headingEl = document.getElementById("statusHeading");
    const msgEl = document.getElementById("statusMsg");

    if (!banner) return;

    headingEl.textContent = heading;
    msgEl.textContent = message;

    banner.classList.remove("status-error");

    if (state === "loading") {
        spinner.classList.remove("d-none");
        successIcon.classList.add("d-none");
    } else if (state === "error") {
        spinner.classList.add("d-none");
        successIcon.classList.remove("d-none");
        successIcon.className = "fa-solid fa-triangle-exclamation success-icon";
        banner.classList.add("status-error");
    } else {
        spinner.classList.add("d-none");
        successIcon.classList.remove("d-none");
        successIcon.className = "fa-solid fa-circle-check success-icon";
    }

    banner.classList.remove("d-none");
}

/**
 * Hides status notification
 */
function hideStatusNotification() {
    const banner = document.getElementById("statusNotification");
    if (banner) banner.classList.add("d-none");
}

function escapeHtml(text) {
    if (!text) return "";
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

