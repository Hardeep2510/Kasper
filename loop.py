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

class ok(Result):
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
        assert isinstance(self.result,ok)
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
    def __post__init__(self):
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
            result=ok(self.future.callback())
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

class loop(asyncio.AbstractEventLoop):
    def __init_(self):
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
                ok,value=self.handle_value(task,value)
                if not ok:
                    return
                log.debug("recieved value %s",value)
                self.tasks.append(task)
                log.debug("recieved value %s",value)
                task.next_value=value

    def _handle_future(self,task:Task,target:Target,value:Any):
        if target=="read":
            log.debug("Appending to read : %s",task)
            self.write.append(task)
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

                case ok(ok_value):
                    log.debug(f"{ok_value=}")
                    value=task.send(ok_value)

                case Exc(error):
                    log.debug(f"{error}")
                    value=task.throw(error)
            return True,value
        
        except StopIteration as ex:
            result=ex.value
            log.debug(f"{task=} terminated with {result=}")
            task.result=ok(result)
            return False,None
        
        except Exception as exception:
            log.debug(f"setting task.result={exception!r}")
            task.result=Exc(exception)
            if task is self.entry_point:
                log.debug("reraising exception")
                raise
            log.error(f"Task exception was never retrieved, {task=}, {exception=!r}")
            return False,None






            








    
    



    












    





