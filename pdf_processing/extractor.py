import pdfplumber


def extract_text_from_pdf(pdf_path):
    """
    Extract and combine text from all pages of a PDF file.

    :param pdf_path: Path to the PDF file.
    :return: Extracted text as a single string.
    """
    combined_text = ""

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    combined_text += page_text + "\n"
    except FileNotFoundError:
        print(f"Error: File not found at '{pdf_path}'")
        return ""
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return ""

    return combined_text
