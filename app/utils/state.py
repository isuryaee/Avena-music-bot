from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from aiogram.fsm.storage.base import BaseStorage, StorageKey
from sqlalchemy.future import select

from app.models import State


class PostgresStorage(BaseStorage):
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]):
        self.session_maker = session_maker

    async def set_state(self, key: StorageKey, state: str = None) -> None:
        async with self.session_maker() as session:
            result = await session.execute(select(State).where(State.user_id == key.user_id))
            user_state = result.scalar()

            state_str = state.state if state else None  

            if user_state:
                user_state.state_data = {"state": state_str}
            else:
                new_state = State(user_id=key.user_id, state_data={"state": state_str})
                session.add(new_state)

            await session.commit()

    async def get_state(self, key: StorageKey):
        async with self.session_maker() as session:
            result = await session.execute(select(State).where(State.user_id == key.user_id))
            user_state = result.scalar()
            return user_state.state_data.get("state") if user_state else None

    async def set_data(self, key: StorageKey, data: dict) -> None:
        async with self.session_maker() as session:
            result = await session.execute(select(State).where(State.user_id == key.user_id))
            user_state = result.scalar()

            if user_state:
                user_state.state_data.update(data)
            else:
                new_state = State(user_id=key.user_id, state_data=data)
                session.add(new_state)

            await session.commit()

    async def get_data(self, key: StorageKey) -> dict:
        async with self.session_maker() as session:
            result = await session.execute(select(State).where(State.user_id == key.user_id))
            user_state = result.scalar()
            return user_state.state_data if user_state else {}

    async def close(self) -> None:
        pass
