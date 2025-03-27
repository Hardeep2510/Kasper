import asyncio
import logging
import time
from dataclasses import dataclass,field
from socket import socket
from typing import Any,Callable,Coroutine,Literal,ClassVar,TypeVar,Awaitable,Generic
from select import select

def setup_logging(log_:logging.Logger):
    formatter=logging.Formatter(
         "{asctime} - {levelname} - {name}:{lineno}.{funcName}() - {message}", style="{"
    )
    #for redirecting the logging messages in console
    handler=logging.StreamHandler()
    handler.setFormatter(formatter)
    log_.addHandler(handler)
    #both log_ and handler accept and show all logs, including debug messages
    for o in log_,handler:
        o.setLevel(logging.DEBUG)

#creating a logger named loop
log=logging.getLogger("loop")
setup_logging(log)

@dataclass
class Result:
    value: Any

class Ok(Result):
    pass


class Exc(Result):
    pass

#Target can only be read or write
Target=Literal["read","write"]
#Accepts any type and returns the same type
T=TypeVar("T")



@dataclass
class Future(Awaitable[T]):
    what: Any
    target: Target

    callback:Callable[[],T]
    result: Result| None=None

    def __await__(self):
        log.debug("awaiting %s",self)
        #making the function a generator,Suspends execution and returns
        yield self
        log.debug(f"returning future result {self.result=}")
        assert isinstance(self.result,Ok)
        return self.result.value
    
    def fileno(self):
        #returns the file descriptor 0 → stdin (Standard Input), 1 → stdout (Standard Output), 2 → stderr (Standard Error)
        return self.what.fileno()
    

@dataclass

class Task(Generic[T]):
    #variable coroutine with its typecheckers
    co: Coroutine[Future, ..., T] = field()
    #class level variable
    counter:ClassVar[int]=0
    
    def __repr__(self):
        return f"Task<{self.co.__name__}#{self.index}>"
    # Gives each instance a unique index, updates the counter
    def __post_init__(self):
        self.index=self.counter
        type(self).counter += 1
        log.debug("created %s", self)
        self.result: Result | None = None
        self.next_value = None
        self.future = None

    #returns  file descriptor
    def fileno(self):
        assert self.future, self
        return self.future.fileno()
    #.send(value) resumes execution and injects value at the yield expression.
    def send(self,value:Any):
        log.debug("sending %s", value)
        return self.co.send(value)
    
    @property
    def done(self):
        return self.result is not None
    
    def step(self):
        try:
            result=Ok(self.future.callback())
        except Exception as ex:
            result=Exc(ex)
        self.next_value=self.future.result = result
    # event loop injects the exception into the coroutine using throw()
    def throw(self,error: Exception):
        return self.co.throw(error)
    
class UniqueList(list[T]):
    def append(self,value:T):
        if value in self:
            raise Exception(f"value {value} already in self {self}")
        super().append(value)

class Loop(asyncio.AbstractEventLoop):
    def __init__(self):
        self.tasks: list[Task]=UniqueList()
        self.read: list[Task]=UniqueList()
        self.write: list[Task]=UniqueList()
        self.entry_point: Task | None = None


    def _run_once(self):
        log.debug("_run_once")
        try:
            task=self.tasks.pop(0)
        except IndexError:
            log.debug("tasks empty")
            return
        value=task.next_value
        match value:
            case Future(_what,target):
                self._handle_future(task,target,value)

            case _:
                ok,value=self._handle_value(task,value)
                if not ok:
                    return
                log.debug("recieved value %s",value)
                self.tasks.append(task)
                log.debug("recieved value %s",value)
                task.next_value=value

    def _handle_future(self,task:Task,target:Target,value:Any):
        if target=="read":
            log.debug("Appending to read : %s",task)
            self.read.append(task)
        if target=="write":
            log.debug("adding to write: %s",task)
            self.write.append(task)
        
            

        log.debug(f"setting future of {task} to {value}")
        task.future = value
        

    def _handle_value(self,task:Task,value:Any):
        try:
            match value:
                case None:
                    value=task.send(None)

                case Ok(ok_value):
                    log.debug(f"{ok_value=}")
                    value=task.send(ok_value)

                case Exc(error):
                    log.debug(f"{error}")
                    value=task.throw(error)
            return True,value
        
        except StopIteration as ex:
            result=ex.value
            log.debug(f"{task=} terminated with {result=}")
            task.result=Ok(result)
            return False,None
        
        except Exception as exception:
            log.debug(f"setting task.result={exception!r}")
            task.result=Exc(exception)
            if task is self.entry_point:
                log.debug("reraising exception")
                raise
            log.error(f"Task exception was never retrieved, {task=}, {exception=!r}")
            return False,None
        

    def select(self):
        log.debug("selecting %s, %s", self.read, self.write)
        if self.read or self.write:
            read_ready, write_ready, _ = select(self.read, self.write, [])
            log.debug("removing from .read, .write: %s, %s",
                      read_ready, write_ready)
            for to_remove, lst in [
                (read_ready, self.read),
                (write_ready, self.write),
            ]:
                for task in to_remove:
                    lst.remove(task)
            all_ready = read_ready + write_ready
            log.debug("adding to tasks: %s", all_ready)
            self.tasks.extend(all_ready)
            for task in all_ready:
                log.debug("stepping %s", task)
                task.step()
        else:
            log.debug("no read")
            time.sleep(0.5)

            

    def create_task(
            self, co: Coroutine[Future, ...,T],_name: str | None=None
    )->Task[T]:
        log.debug("creating task for %s", co)
        task:Task[T]=Task(co)
        log.debug("adding to tasks : %s",task)
        self.tasks.append(task)
        return task
    
    def run_forever(self)-> None:
        while True:
            if self.tasks:
                self._run_once()
            else:
                self.select()

    def run_until_complete(self,co:Coroutine[Future, ...,T])->T:
        task:Task=self.create_task(co)
        self.entry_point=task
        log.debug("adding to tasks: %s", task)
        while not task.done:
            if self.tasks:
                self._run_once()

            else:
                self.select()

        assert task.result is not None

        assert isinstance(task.result,Ok)
        return task.result.value
    
    def sock_accept(self,server:socket)->Future[tuple[socket,tuple[str,int]]]:
        return Future(server,"read",server.accept)
    
    def sock_recv(self, socket_: socket, size: int) -> Future[bytes]:
        return Future(socket_, "read", lambda: socket_.recv(size))
    
     
    def sock_sendall(self, socket_: socket, payload: bytes) -> Future[None]:
        return Future(socket_, "write", lambda: socket_.sendall(payload)) 
    


loop = Loop()

def run(co: Coroutine[Future, ..., T]) -> T:
    return loop.run_until_complete(co)
 
 
def get_event_loop():
    return loop
 
 
def unreachable():
    assert False, "unreachable"


