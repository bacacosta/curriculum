from io import BytesIO

from pypdf import PdfReader


def test_empty_pdf_has_only_page_number(client):
    response = client.get('/export.pdf')
    assert response.status_code == 200
    pdf = PdfReader(BytesIO(response.content))
    assert len(pdf.pages) == 1
    assert pdf.pages[0].extract_text().strip() == '1'


def test_pdf_export_contents_pagination_and_download(client):
    for field, value in {
        'name': 'Ada Example', 'address': 'First Street, Berlin',
        'email': 'ada@example.com', 'phone': '0049 123456',
    }.items():
        client.post(f'/header/{field}/edit', data={field: value})
    for index in range(12):
        client.post('/sections', data={'title': f'Experience {index}'})
        section_id = client.get('/api/resume').json()['sections'][-1]['id']
        client.post(f'/sections/{section_id}/bullets', data={'content': f'Built project {index}'})
        bullet_id = client.get('/api/resume').json()['sections'][-1]['children'][0]['id']
        client.post(f'/sections/{section_id}/bullets', data={'content': 'Nested achievement', 'parent_id': bullet_id})

    response = client.get('/export.pdf')
    assert response.status_code == 200
    assert response.headers['content-type'] == 'application/pdf'
    assert response.headers['content-disposition'] == 'attachment; filename="resume.pdf"'
    assert response.content.startswith(b'%PDF-')
    pdf = PdfReader(BytesIO(response.content))
    assert len(pdf.pages) >= 2
    text = '\n'.join(page.extract_text() for page in pdf.pages)
    for value in ['Ada Example', 'First Street, Berlin', 'ada@example.com', '0049 123456',
                  'Experience 0', 'Experience 11', 'Built project 11', 'Nested achievement']:
        assert value in text
    for unwanted in ['Resume editor', 'http://', 'Export PDF', 'Export to web', 'Add section']:
        assert unwanted not in text
    for number, page in enumerate(pdf.pages, 1):
        assert page.extract_text(extraction_mode='layout').strip().splitlines()[-1].strip() == str(number)
        assert abs(float(page.mediabox.width) - 595.28) < 2
        assert abs(float(page.mediabox.height) - 841.89) < 2
