import datetime
import time
from django.contrib.auth import logout, authenticate, login
from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.decorators import login_required
from scheduler.forms import EventForm, ScheduleForm, AddFriendForm
from django.contrib.auth.models import User
from scheduler.models import *
from scheduler.functions import datetime_to_week, get_times_when_busy
from itertools import chain

def home_view(request):
    if request.user.is_authenticated():
        return redirect('/accounts/profile')
    return render(request,"scheduler/base.html")

def logout_view(request):
    logout(request)
    return render(request, "scheduler/loggedout.html")

def is_loggedin_view(request):
    if request.user.is_authenticated():
        return HttpResponse("You are logged in.")
    else:
        return HttpResponse("You are not logged in.")

def register_view(request):
    if request.user.is_authenticated():
        return redirect('/')
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            new_user = form.save()
            return HttpResponseRedirect("/")
    else:
        form = UserCreationForm()
    return render(request, "scheduler/register.html", {
        'form': form,
    })

@login_required
def account_view(request):
    schedules = Schedule.objects.filter(creator=request.user)
    return render(request, "scheduler/account.html",{'schedules':schedules})

@login_required
def create_event_view(request,scheduleid):
    schedule = get_object_or_404(Schedule, id=scheduleid) # The parent schedule
    # If the current user does not own the schedule, do not allow them to create an event on it.
    if schedule.creator != request.user:
        return render(request, "scheduler/errorpage.html", {'message':"PERMISSION DENIED"})
    if request.method == 'POST':
        form = EventForm(data=request.POST) # Load the form
        if form.is_valid():
            event = form.save(commit = False) # Get an event with the form data (don't commit to db yet)
            event.schedule = schedule # Set the parent schedule
            event.save() # NOW we can save to the database.
            return redirect("/schedule/"+str(event.schedule.id))
        else:
            return render(request, "scheduler/createevent.html",{'form':form,'schedule':schedule})
    else:
        form = EventForm()
        return render(request, "scheduler/createevent.html",{'form':form,'schedule':schedule})

@login_required
def create_schedule_view(request):
    if request.method == 'POST':
        form = ScheduleForm(data=request.POST) #Load form
        if form.is_valid():
            schedule = form.save(commit = False) #get schedule with form data, doesnt commit
            schedule.creator = request.user #add creator id
            schedule.save() #commit to db
            return redirect("/schedule/"+str(schedule.id)) # Redirect to the view page for that schedule
        else:
            return render(request, "scheduler/createschedule.html",{'form':form})
    else:
        form = ScheduleForm()
        return render(request, "scheduler/createschedule.html",{'form':form})

@login_required
def edit_schedule_view(request, scheduleid):
    schedule = get_object_or_404(Schedule, id=scheduleid)
    if schedule.creator != request.user:
        return render(request, "scheduler/errorpage.html", {'message':"PERMISSION DENIED"})
    if request.method == 'POST':
        form = ScheduleForm(instance=schedule, data=request.POST)
        if form.is_valid():
            form.save()
            return redirect("/schedule/"+str(schedule.id))
        else:
            return render(request, "scheduler/createschedule.html",{'form':form, 'edit':'edit', 'schedule':schedule})
    else:
        form = ScheduleForm(instance=schedule)
        return render(request, "scheduler/createschedule.html",{'form':form, 'edit':'edit', 'schedule':schedule})


@login_required
def edit_event_view(request, eventid):
    event = get_object_or_404(Event, id=eventid)
    if event.schedule.creator != request.user:
        return render(request, "scheduler/errorpage.html", {'message':"PERMISSION DENIED"})
    if request.method == 'POST':
        form = EventForm(instance=event,data=request.POST)
        if form.is_valid():
            form.save()
            return redirect("/schedule/"+str(event.schedule.id))
        else:
            return render(request, "scheduler/createevent.html",{'form':form,'edit':'edit','event':event})
    else:
        form = EventForm(instance=event)
        return render(request, "scheduler/createevent.html",{'form':form,'edit':'edit','event':event})

def schedule_compare_view(request, otheruserid, viewinguserid, starttime=None):
    if starttime == None:
        starttime = int(time.time())

    user1 = get_object_or_404(User, id=otheruserid)
    user1profile = Profile.objects.of_user(user1)
    user2 = get_object_or_404(User, id=viewinguserid)
    user2profile = Profile.objects.of_user(user2)
    week = datetime_to_week(datetime.datetime.fromtimestamp(float(starttime)))

    days = []
    for day in week:
        user1events = Event.objects.on_date(day, user1profile.main_schedule)
        user2events = Event.objects.on_date(day, user2profile.main_schedule)
        allevents = list(chain(user1events,user2events))

        busy_times = get_times_when_busy(allevents)

        days.append((day, busy_times))

    return render(request, "scheduler/schedule.html", {'events':days, 'starttime':starttime,'otheruser':user1, 'viewinguser':user2, 'comparing':True})

def schedule_view(request, scheduleid, view=0, starttime=None):
    if starttime == None:
        starttime = int(time.time())
    week = datetime.datetime.fromtimestamp(float(starttime))
    schedule = get_object_or_404(Schedule, id=scheduleid)
    canView = False
    isOwner = False
    isMainSchedule = False
    # Schedule is public, allow anyone to view it
    if schedule.visibility == schedule.VISIBILITY_PUBLIC:
        canView = True
    elif schedule.visibility == schedule.VISIBILITY_FRIENDSONLY:
        #set canView true if the request user and schedule creator are friends:
        if schedule.creator == request.user:
            canView = True
            isOwner = True
        else:
            canView = Friend.objects.are_friends(request.user, schedule.creator)
        #if the request user is the creator set canView true:

    # If the schedule is private, only allow the owner to view it.
    elif schedule.visibility == schedule.VISIBILITY_PRIVATE:
        if schedule.creator == request.user: # If the current user is the owner
            canView = True
        else:
            canView = False
    if canView:
        if not isOwner:
            isOwner = (schedule.creator == request.user)
        if isOwner:
            profile = Profile.objects.of_user(schedule.creator)
            if profile.main_schedule == None:
                isMainSchedule = False
            elif profile.main_schedule == schedule:
                isMainSchedule = (profile.main_schedule == schedule)

        week = datetime_to_week(week)
        events = []

        # Fill the events array with tuples containing a datetime object and all the events happening on that day
        for day in week:
            events.append((day, Event.objects.on_date(day, schedule)))

        return render(request, "scheduler/schedule.html",{'schedule':schedule, 'events':events, 'starttime':starttime, 'isowner':isOwner, 'ismainschedule':isMainSchedule})
    else:
        return render(request,"scheduler/errorpage.html",{'message':"PERMISSION DENIED"})

@login_required
def friends_view(request):
    friends = Friend.objects.all_friends_for_user(request.user)
    pending_requests = []
    sent_requests = []
    accepted_friends = []
    for friend in friends:

        # Set friend.other so that the view knows which name to show in the friends list.
        if friend.creator == request.user:
            friend.other = 0
        else:
            friend.other = 1

        if friend.status == Friend.STATUS_SENT:
            if friend.creator == request.user:
                sent_requests.append(friend)
            else:
                pending_requests.append(friend)
        elif friend.status == Friend.STATUS_ACCEPTED or friend.status == Friend.STATUS_MATCHED:
            accepted_friends.append(friend)

    return render(request,"scheduler/friends.html", {'friends': accepted_friends,'sent_requests':sent_requests, 'pending_requests':pending_requests})

@login_required
def friends_accept_view(request, friendid):
    friend = get_object_or_404(Friend, id=friendid)
    if friend.status != Friend.STATUS_SENT:
        raise Http404
    if friend.friend == request.user:
        friend.status = Friend.STATUS_ACCEPTED
        friend.save()
    else:
        return render(request,"scheduler/errorpage.html",{'message':"PERMISSION DENIED"})
    return redirect("/friends")

@login_required
def friends_decline_view(request, friendid):
    friend = get_object_or_404(Friend, id=friendid)
    if friend.status != Friend.STATUS_SENT:
        raise Http404
    if friend.friend == request.user:
        friend.delete()
    else:
        return render(request,"scheduler/errorpage.html",{'message':"PERMISSION DENIED"})
    return redirect("/friends")


@login_required
def friends_add_view(request):
    if request.method == "POST":
        form = AddFriendForm(request.POST)
        if form.is_valid():
            # Get the friend relationship if it already exists
            friend = Friend.objects.get_friend_object(request.user, form.get_newfriend_user())
            # If the relationship did not previously exist, create it as a request with the current user as the creator.
            if friend == None:
                if form.get_newfriend_user() == request.user:
                    return render(request,"scheduler/errorpage.html",{'message':"You can't send a friend request to yourself."})
                friend = Friend(creator=request.user, friend=form.get_newfriend_user())
                friend.save()
                return redirect("/friends/")
            else: # If the relationship already exists...
                # See if it was already accepted/matched and tell them they are already friends
                if friend.status == Friend.STATUS_ACCEPTED or friend.status == Friend.STATUS_MATCHED:
                    return render(request, "scheduler/errorpage.html",{'message':"You are already friends with this user"})
                # It was a sent friend request
                elif friend.status == Friend.STATUS_SENT:
                    # If it was sent by the current user, tell them they can't send another.
                    if friend.creator == request.user:
                        return render(request,"scheduler/errorpage.html",{'message':"You already sent a friend request to this user."})
                    # Otherwise, match the two up and update the original friend request.
                    else:
                        # The other user sent this friend request. Update it to STATUS_MATCHED.
                        friend.status = Friend.STATUS_MATCHED
                        friend.save()
                        return redirect("/friends/")
    else:
        form = AddFriendForm()

    return render(request, "scheduler/addfriend.html", {"form":form})


def account_page_view(request, userid):
    #Get all the schedules from the user indicated:
    user = get_object_or_404(User, id=userid)
    schedules = Schedule.objects.filter(creator=user, visibility=Schedule.VISIBILITY_PUBLIC)
    main_schedule = Profile.objects.of_user(user).main_schedule
    # Check if the user viewing the page has a main schedule
    request_user_has_main_schedule = False
    # If they're not authenticated, they can't possibly have a main schedule.
    if request.user.is_authenticated():
        # Check the request user's profile to see if they have a main schedule.
        request_user_profile = Profile.objects.of_user(request.user)
        # If the request user's main schedule is NOT None, then they have a main schedule.
        if not request_user_profile.main_schedule == None:
            request_user_has_main_schedule = True


    #get the friend object of that user
    if request.user.is_authenticated():
        #if the request user is the owner of the profile then they can view friends only schedules and private schedules
        if request.user == user:
            #gets private schedules:
            private = Schedule.objects.filter(creator=userid, visibility=Schedule.VISIBILITY_PRIVATE)
            #gets friends only schedules:
            friendsOnly = Schedule.objects.filter(creator=userid, visibility=Schedule.VISIBILITY_FRIENDSONLY)
            #returns public, friends only and private schedules:
            return render(request, "scheduler/user.html",{'pageuser':user, 'schedules':schedules, 'friendsOnly':friendsOnly, 'private':private, 'main':main_schedule, 'is_self':True, 'request_user_has_main_schedule':request_user_has_main_schedule})
            #allows friend only schedule viewing:
        else:
            #if the request user isnt the owner of the profile see if they are friends.
            if Friend.objects.are_friends(request.user, user):
                #get friends only schedules:
                friendsOnly = Schedule.objects.filter(creator=userid, visibility=Schedule.VISIBILITY_FRIENDSONLY)
                #returns public and friendsonly schedules:
                return render(request, "scheduler/user.html",{'pageuser':user, 'schedules':schedules, 'friendsOnly':friendsOnly, 'main':main_schedule,'request_user_has_main_schedule':request_user_has_main_schedule})
    #returns only public schedules: (Happens when user is not authenticated or user is not friends with the account we're viewing)
    return render(request, "scheduler/user.html",{'pageuser':user, 'schedules':schedules, 'main':main_schedule,'request_user_has_main_schedule':request_user_has_main_schedule})

def set_main_schedule_view(request, scheduleid):
    schedule = get_object_or_404(Schedule, id=scheduleid)
    if not schedule.creator == request.user:
        return render("scheduler/errorpage.html",{'message':"PERMISSION DENIED"})
    else:
        profile = Profile.objects.of_user(request.user)
        profile.main_schedule = schedule
        profile.save()
        return redirect("/schedule/"+str(schedule.id))

def delete_schedule_view(request, scheduleid):
    schedule = get_object_or_404(Schedule, id=scheduleid)
    if not schedule.creator == request.user:
        return render(request, "scheduler/errorpage.html",{'message':"PERMISSION DENIED"})
    else:
        if Profile.objects.of_user(schedule.creator).main_schedule == schedule:
            return render(request, "scheduler/errorpage.html",{'message':"You can't delete your main schedule."})

        else:
            schedule.delete()
    return redirect("/accounts/profile/")

def stylesheet_view(request, styleid):
    styleid = int(styleid)
    if styleid == 0:
        return render(request, "scheduler/basestyle.css", content_type="text/css")
    if styleid == 1:
        return render(request, "scheduler/schedulestyle.css", content_type="text/css")
    raise Http404

def api_view(request, apikey, format, commandrequested):
    pass
