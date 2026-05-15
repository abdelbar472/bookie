"""gRPC server for Book Service V3."""
import asyncio
import logging
from concurrent import futures
from typing import Optional

import grpc

from proto import book_v3_pb2, book_v3_pb2_grpc
from database import db
from models.book import BookProfile

logger = logging.getLogger(__name__)


class BookV3Service(book_v3_pb2_grpc.BookV3ServiceServicer):
    async def GetBookByWorkId(self, request, context):
        work_id = request.work_id
        try:
            book_data = await db.get_book(work_id)
            if not book_data:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details("Book not found")
                return book_v3_pb2.BookV3Payload()

            return book_v3_pb2.BookV3Payload(
                work_id=book_data.get("work_id", ""),
                title=book_data.get("title", ""),
                primary_author=book_data.get("primary_author", ""),
                authors=book_data.get("authors", []),
                description=book_data.get("description", ""),
                genres=book_data.get("genres", []),
                themes=book_data.get("themes", []),
                rag_document=book_data.get("rag_document", ""),
            )
        except Exception as exc:
            logger.error("Error in GetBookByWorkId: %s", exc)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Internal error")
            return book_v3_pb2.BookV3Payload()

    async def ListBooks(self, request, context):
        skip = request.skip
        limit = request.limit
        try:
            books_data = await db.list_books(skip=skip, limit=limit)
            books = []
            for book_data in books_data:
                books.append(book_v3_pb2.BookV3Payload(
                    work_id=book_data.get("work_id", ""),
                    title=book_data.get("title", ""),
                    primary_author=book_data.get("primary_author", ""),
                    authors=book_data.get("authors", []),
                    description=book_data.get("description", ""),
                    genres=book_data.get("genres", []),
                    themes=book_data.get("themes", []),
                    rag_document=book_data.get("rag_document", ""),
                ))
            return book_v3_pb2.BookV3ListResponse(books=books, total=len(books))
        except Exception as exc:
            logger.error("Error in ListBooks: %s", exc)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Internal error")
            return book_v3_pb2.BookV3ListResponse()

    async def SearchBooks(self, request, context):
        query = request.query
        skip = request.skip
        limit = request.limit
        try:
            # For simplicity, use text search or something
            # Assuming db has a search method
            books_data = await db.search_books(query, skip=skip, limit=limit)
            books = []
            for book_data in books_data:
                books.append(book_v3_pb2.BookV3Payload(
                    work_id=book_data.get("work_id", ""),
                    title=book_data.get("title", ""),
                    primary_author=book_data.get("primary_author", ""),
                    authors=book_data.get("authors", []),
                    description=book_data.get("description", ""),
                    genres=book_data.get("genres", []),
                    themes=book_data.get("themes", []),
                    rag_document=book_data.get("rag_document", ""),
                ))
            return book_v3_pb2.BookV3ListResponse(books=books, total=len(books))
        except Exception as exc:
            logger.error("Error in SearchBooks: %s", exc)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Internal error")
            return book_v3_pb2.BookV3ListResponse()


async def start_grpc_server(host: str = "0.0.0.0", port: int = 50057):
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
    book_v3_pb2_grpc.add_BookV3ServiceServicer_to_server(BookV3Service(), server)
    server.add_insecure_port(f"{host}:{port}")
    await server.start()
    logger.info("Book V3 gRPC server started on %s:%s", host, port)
    return server
