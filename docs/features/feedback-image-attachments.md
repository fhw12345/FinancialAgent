# Feature: Feedback Image Attachments

> **Status**: Implemented
> **Created**: 2025-10-30
> **Last Updated**: 2025-11-19
> **Owner**: Financial Agent Team

## Context

Users need the ability to attach screenshots and images when submitting feedback to better illustrate bugs, UI issues, or feature suggestions. Currently, feedback is limited to text-only descriptions, which makes it harder to understand visual problems.

**User Story**:
As a user reporting a bug or UI issue, I want to attach screenshots directly to my feedback, so that developers can see exactly what I'm describing without additional back-and-forth communication.

**Background**:
- Current feedback form only accepts title and description (text)
- Users mentioned: "Feedback should support image attachments"
- Common use cases:
  - UI layout bugs (collapse arrow obscured, table formatting issues)
  - Chart rendering problems
  - Visual design suggestions
  - Mobile responsiveness issues

**Related Features**:
- Feedback Platform (existing: `/docs/features/feedback-platform.md`)
- Alibaba Cloud OSS storage (already configured for Langfuse)

---

## Problem Statement

**Current Limitations**:
1. ❌ No way to attach screenshots to feedback
2. ❌ Developers must recreate reported issues without visual context
3. ❌ Increases back-and-forth communication for visual bugs
4. ❌ Reduces feedback quality and actionability

**Impact**:
- Slower bug resolution times
- Misinterpretation of user feedback
- Frustration from users trying to describe visual issues in text

---

## Proposed Solution

### High-Level Approach

Add image upload capability to the feedback submission form, with files stored in Alibaba Cloud OSS (same bucket as Langfuse events).

**Key Components**:
1. **Frontend**: File input with drag-and-drop support
2. **Backend**: File upload endpoint with validation
3. **Storage**: Use Alibaba Cloud OSS bucket (`financial-agent-oss`)
4. **Database**: Store OSS URLs in feedback items
5. **Display**: Show thumbnails in feedback list/detail views

### Technical Architecture

```
User Browser
    ↓ (Upload image)
Frontend Form (/src/components/feedback/SubmitFeedbackForm.tsx)
    ↓ (POST /api/feedback/upload-attachment)
Backend API (/api/feedback.py)
    ↓ (Validate + Upload)
OSS Service (/services/oss_service.py)
    ↓ (Store file)
Alibaba Cloud OSS (financial-agent-oss/financial-agent/feedbacks/)
    ↓ (Return URL)
MongoDB (feedback collection)
    ↓ (Store attachment URLs)
Feedback Detail View
    ↓ (Display images)
User/Admin
```

### Data Flow

1. **Upload Phase**:
   - User selects image(s) → Frontend validates type/size
   - Upload to `/api/feedback/upload-attachment` → Returns OSS URL
   - Frontend stores URL in form state

2. **Submission Phase**:
   - User submits feedback → Includes attachment URLs
   - Backend validates URLs are from our OSS bucket
   - Save feedback with `attachments: [url1, url2, ...]`

3. **Display Phase**:
   - Feedback list shows thumbnail previews
   - Click to view full-size image in new tab
   - 7-day signed URLs for secure access

---

## Implementation Plan

### Phase 1: Backend Storage Setup (Day 1-2)

**Config**: Add `feedback_attachments_prefix`, `max_attachment_size_mb: 10`, `allowed_attachment_types`

**OSSService**: `upload_feedback_attachment(file, filename, content_type) -> url` using `oss2` library

**Storage**: OSS bucket `financial-agent-oss`, endpoint `https://oss-cn-shanghai.aliyuncs.com`, prefix `financial-agent/feedbacks/`

### Phase 2: Backend Model & API (Day 2-3)

**Models**: Add `attachments: list[str]` (max 5) to FeedbackItemCreate and FeedbackItem

**API**: `POST /api/feedback/upload-attachment` - validate type (PNG/JPG/GIF/WebP), size (10MB max), upload to OSS, return URL. Modify submit to validate URLs match OSS bucket pattern.

### Phase 3: Frontend Form Enhancement (Day 4-5)

**SubmitFeedbackForm.tsx**: Add `attachments[]` and `uploadingFiles` state, file input (accept images, multiple), upload handler, thumbnails with remove button

### Phase 4: Feedback Display Enhancement (Day 6)

**FeedbackItem.tsx**: Display title, description, type, date, attachments as clickable thumbnails (3-column grid)

---

## Data Models

**Backend**: `FeedbackItem` - id, title, description, type, `attachments: list[str] = []` (NEW: OSS URLs), created_at, updated_at, user_id, status

**Frontend**: `FeedbackItemCreate` - title, description, type, `attachments?: string[]`. `FeedbackItem` - same fields with `attachments: string[]`

---

## API Endpoints

### Upload Attachment

`POST /api/feedback/upload-attachment` (multipart/form-data)

**Response**: `{ "upload_url": "https://financial-agent-oss.oss-cn-shanghai.aliyuncs.com/financial-agent/feedbacks/...", "public_url": "...", "object_key": "...", "expires_in": 300 }`

**Status Codes**: 200 (Success), 400 (Invalid type/size), 413 (Too large), 500 (Upload failed)

### Submit Feedback (Modified)

`POST /api/feedback/submit` now accepts `attachments?: string[]` (array of OSS URLs)

---

## Security Considerations

**Type Validation**: Only image MIME types, verify magic numbers, block SVG (XSS risk)

**Size Limits**: Max 10MB/file, max 5 files/feedback, total 50MB

**Filename Sanitization**: Generate `{timestamp}-{uuid}.{ext}`, never use user-provided names

**URL Validation**: Only accept URLs from our OSS bucket domain

**Access Control**: Signed URLs (7-day expiration), private bucket, `feedback-attachments/` prefix, optional 90-day lifecycle policy

---

## Performance Considerations

**Client-Side Compression**: Resize to max 1920px width, target <500KB via Canvas API

**Lazy Loading**: Intersection observer for thumbnails, full-size on click

**Future**: Alibaba Cloud CDN, server-side thumbnail generation (200x200)

---

## Testing Strategy

**Backend Unit Tests**: `test_upload_valid_image`, `test_upload_invalid_type`, `test_upload_oversized_file`, `test_generate_unique_filename`, `test_signed_url_generation`, `test_submit_feedback_with_attachments`, `test_validate_attachment_urls`

**Frontend Integration Tests**: Upload single/multiple images, remove attachment, submit with attachments, display attachments

**Manual Testing**: Upload PNG/JPG/GIF/WebP (success), upload PDF/TXT (fail), 11MB file (fail), 6 files (fail), remove before submit, view thumbnails, click for full-size, mobile responsive

---

## Acceptance Criteria

### Must Have (MVP)

- [x] Users can upload 1-5 images per feedback
- [x] Supported formats: PNG, JPG, GIF, WebP
- [x] Max file size: 10MB per image
- [x] Images stored in Alibaba Cloud OSS
- [x] Feedback form shows uploaded thumbnails with remove button
- [x] Submitted feedback includes attachment URLs in database
- [x] Feedback display shows attachments as clickable thumbnails
- [x] Error handling for invalid files (type, size)
- [x] Loading states during upload

### Nice to Have (Future)

- [ ] Drag-and-drop file upload
- [ ] Client-side image compression
- [ ] Thumbnail generation on server
- [ ] Image annotation/markup tool
- [ ] Video attachment support
- [ ] Clipboard paste image support

---

## Risks & Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Storage costs escalate | Medium | Low | Implement 90-day lifecycle policy, monitor usage |
| Abuse (spam uploads) | High | Medium | Rate limiting, require authentication, max 5 files |
| Large file uploads slow down UX | Medium | High | Client-side compression, progress bars |
| OSS service downtime | High | Low | Graceful degradation, retry logic, queue uploads |
| XSS via SVG uploads | High | Medium | Block SVG, validate MIME types, sanitize metadata |

---

## Rollout Plan

**Development** (1 week): Backend storage + API (Day 1-2), Frontend form (Day 3-4), Display updates (Day 5), Testing (Day 6), Documentation (Day 7)

**Test**: Deploy to K8s test namespace, verify OSS connectivity, test real uploads

**Production**: Backend first (backward compatible), frontend after validation, monitor error rates and storage

**Monitoring**: Upload success rate, average file size, total storage (GB), failed upload reasons, feedback with/without attachments (%)

---

## Dependencies

### External Services

- **Alibaba Cloud OSS**: Dedicated feedback storage bucket
  - Bucket: `financial-agent-oss`
  - Region: `cn-shanghai`
  - Endpoint: `oss-cn-shanghai.aliyuncs.com`
  - Object prefix: `financial-agent/feedbacks/`
  - Access: Presigned URLs (private bucket)
  - Access via `oss2` Python library

### Python Libraries

- `oss2`: Already installed (used by Langfuse)
- `python-magic`: For MIME type validation (optional)

### Frontend Libraries

- No new dependencies needed
- Use native `<input type="file">` API
- Consider `react-dropzone` for drag-and-drop (optional)

---

## Success Metrics

### Quantitative

- **Target**: 50% of bug reports include screenshots within 30 days
- **Upload Success Rate**: >95%
- **Average Feedback Resolution Time**: Reduce by 30%
- **User Satisfaction**: Feedback form NPS score improves

### Qualitative

- Developers report better understanding of visual bugs
- Reduced back-and-forth in feedback discussions
- Improved bug reproduction rates

---

## Future Enhancements

1. **Video Attachments**: Support screen recordings (MP4, WebM)
2. **Image Annotation**: Allow users to mark up screenshots with arrows/text
3. **Clipboard Paste**: Paste images directly from clipboard
4. **Automatic Screenshots**: Browser extension to capture screenshots
5. **OCR for Text in Images**: Extract text from screenshots for search
6. **Thumbnail Generation**: Server-side thumbnail creation for faster loading

---

## References

- Existing Feedback Platform: `/docs/features/feedback-platform.md`
- Alibaba Cloud OSS Documentation: https://www.alibabacloud.com/help/en/oss
- OSS Python SDK: https://help.aliyun.com/document_detail/32026.html
- File Upload Best Practices: https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html
