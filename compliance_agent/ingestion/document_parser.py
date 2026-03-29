"""Document parsing utilities for PDF, DOCX, and lightweight text files."""

import re
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass

try:
    import pdfplumber
    import PyPDF2
except ImportError:
    pdfplumber = None
    PyPDF2 = None

try:
    from docx import Document
except ImportError:
    Document = None


@dataclass
class DocumentChunk:
    """Represents a chunk of text from a document."""
    chunk_id: str
    doc_type: str  # "policy" or "response"
    section_title: str
    page_range: str
    text: str
    metadata: Dict


class DocumentParser:
    """Parses PDF and DOCX documents into structured chunks."""
    
    def __init__(self):
        self.supported_formats = [".pdf", ".docx", ".txt"]
    
    def parse(self, file_path: str, doc_type: str = "policy") -> List[DocumentChunk]:
        """
        Parse a document and return chunks.
        
        Args:
            file_path: Path to the document
            doc_type: "policy" or "response"
        
        Returns:
            List of DocumentChunk objects
        """
        path = Path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"Document not found: {file_path}")
        
        suffix = path.suffix.lower()
        
        if suffix == ".pdf":
            return self._parse_pdf(path, doc_type)
        elif suffix == ".docx":
            return self._parse_docx(path, doc_type)
        elif suffix == ".txt":
            return self._parse_text(path, doc_type)
        else:
            raise ValueError(f"Unsupported file format: {suffix}")
    
    def _parse_pdf(self, file_path: Path, doc_type: str) -> List[DocumentChunk]:
        """Parse PDF file."""
        chunks = []
        
        # Try pdfplumber first (better text extraction)
        if pdfplumber:
            try:
                return self._parse_pdf_pdfplumber(file_path, doc_type)
            except Exception as e:
                print(f"pdfplumber failed, trying PyPDF2: {e}")
        
        # Fallback to PyPDF2
        if PyPDF2:
            return self._parse_pdf_pypdf2(file_path, doc_type)
        
        raise ImportError("No PDF parsing library available. Install pdfplumber or PyPDF2.")
    
    def _parse_pdf_pdfplumber(self, file_path: Path, doc_type: str) -> List[DocumentChunk]:
        """Parse PDF using pdfplumber."""
        chunks = []
        current_section = "Introduction"
        page_start = 1
        
        with pdfplumber.open(file_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                text = page.extract_text()
                
                if not text:
                    continue
                
                # Try to detect section headers (all caps, bold-like patterns)
                lines = text.split('\n')
                section_text = []
                
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    
                    # Detect section headers (heuristic: short lines, all caps, or numbered)
                    if self._is_section_header(line):
                        # Save previous section if it has content
                        if section_text:
                            chunk_text = '\n'.join(section_text)
                            chunk_id = f"{doc_type}_chunk_{len(chunks)}"
                            chunks.append(DocumentChunk(
                                chunk_id=chunk_id,
                                doc_type=doc_type,
                                section_title=current_section,
                                page_range=f"{page_start}-{page_num-1}",
                                text=chunk_text,
                                metadata={"page": page_num, "file": str(file_path)}
                            ))
                            section_text = []
                            page_start = page_num
                        
                        current_section = line[:100]  # Limit section title length
                    
                    section_text.append(line)
                
                # Add remaining text from last page
                if section_text and page_num == len(pdf.pages):
                    chunk_text = '\n'.join(section_text)
                    chunk_id = f"{doc_type}_chunk_{len(chunks)}"
                    chunks.append(DocumentChunk(
                        chunk_id=chunk_id,
                        doc_type=doc_type,
                        section_title=current_section,
                        page_range=f"{page_start}-{page_num}",
                        text=chunk_text,
                        metadata={"page": page_num, "file": str(file_path)}
                    ))
        
        return chunks
    
    def _parse_pdf_pypdf2(self, file_path: Path, doc_type: str) -> List[DocumentChunk]:
        """Parse PDF using PyPDF2."""
        chunks = []
        
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            current_section = "Introduction"
            page_start = 1
            
            for page_num, page in enumerate(pdf_reader.pages, start=1):
                text = page.extract_text()
                
                if not text:
                    continue
                
                lines = text.split('\n')
                section_text = []
                
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    
                    if self._is_section_header(line):
                        if section_text:
                            chunk_text = '\n'.join(section_text)
                            chunk_id = f"{doc_type}_chunk_{len(chunks)}"
                            chunks.append(DocumentChunk(
                                chunk_id=chunk_id,
                                doc_type=doc_type,
                                section_title=current_section,
                                page_range=f"{page_start}-{page_num-1}",
                                text=chunk_text,
                                metadata={"page": page_num, "file": str(file_path)}
                            ))
                            section_text = []
                            page_start = page_num
                        
                        current_section = line[:100]
                    
                    section_text.append(line)
                
                if section_text and page_num == len(pdf_reader.pages):
                    chunk_text = '\n'.join(section_text)
                    chunk_id = f"{doc_type}_chunk_{len(chunks)}"
                    chunks.append(DocumentChunk(
                        chunk_id=chunk_id,
                        doc_type=doc_type,
                        section_title=current_section,
                        page_range=f"{page_start}-{page_num}",
                        text=chunk_text,
                        metadata={"page": page_num, "file": str(file_path)}
                    ))
        
        return chunks
    
    def _parse_docx(self, file_path: Path, doc_type: str) -> List[DocumentChunk]:
        """Parse DOCX file."""
        if not Document:
            raise ImportError("python-docx not installed")
        
        doc = Document(file_path)
        chunks = []
        current_section = "Introduction"
        section_text = []
        
        for para in doc.paragraphs:
            text = para.text.strip()
            
            if not text:
                continue
            
            # Check if paragraph is a heading
            if para.style.name.startswith('Heading'):
                # Save previous section
                if section_text:
                    chunk_text = '\n'.join(section_text)
                    chunk_id = f"{doc_type}_chunk_{len(chunks)}"
                    chunks.append(DocumentChunk(
                        chunk_id=chunk_id,
                        doc_type=doc_type,
                        section_title=current_section,
                        page_range="N/A",  # DOCX doesn't have pages
                        text=chunk_text,
                        metadata={"style": para.style.name, "file": str(file_path)}
                    ))
                    section_text = []
                
                current_section = text[:100]
            else:
                section_text.append(text)
        
        # Add final section
        if section_text:
            chunk_text = '\n'.join(section_text)
            chunk_id = f"{doc_type}_chunk_{len(chunks)}"
            chunks.append(DocumentChunk(
                chunk_id=chunk_id,
                doc_type=doc_type,
                section_title=current_section,
                page_range="N/A",
                text=chunk_text,
                metadata={"file": str(file_path)}
            ))
        
        return chunks

    def _parse_text(self, file_path: Path, doc_type: str) -> List[DocumentChunk]:
        """Parse plain-text fixture files used for lightweight demos and tests."""
        text = file_path.read_text(encoding="utf-8")
        chunks = []
        current_section = "Introduction"
        section_text = []

        for raw_line in text.splitlines():
            line = raw_line.strip()

            if not line:
                continue

            if self._is_section_header(line):
                if section_text:
                    chunk_id = f"{doc_type}_chunk_{len(chunks)}"
                    chunks.append(DocumentChunk(
                        chunk_id=chunk_id,
                        doc_type=doc_type,
                        section_title=current_section,
                        page_range="N/A",
                        text="\n".join(section_text),
                        metadata={"file": str(file_path), "format": "txt"},
                    ))
                    section_text = []
                current_section = line[:100]
                continue

            section_text.append(line)

        if section_text:
            chunk_id = f"{doc_type}_chunk_{len(chunks)}"
            chunks.append(DocumentChunk(
                chunk_id=chunk_id,
                doc_type=doc_type,
                section_title=current_section,
                page_range="N/A",
                text="\n".join(section_text),
                metadata={"file": str(file_path), "format": "txt"},
            ))

        return chunks
    
    def _is_section_header(self, line: str) -> bool:
        """Heuristic to detect section headers."""
        # Short lines that are all caps or start with numbers
        if len(line) < 100 and (line.isupper() or re.match(r'^\d+[\.\)]\s+', line)):
            return True
        
        # Lines that match common header patterns
        header_patterns = [
            r'^[A-Z][A-Z\s]{2,}$',  # All caps words
            r'^\d+\.\s+[A-Z]',  # Numbered sections
            r'^[IVX]+\.\s+[A-Z]',  # Roman numerals
        ]
        
        for pattern in header_patterns:
            if re.match(pattern, line):
                return True
        
        return False
