from moviepy.editor import VideoFileClip
import speech_recognition as sr
import os

def extract_dialogue(video_path):
    """
    Simple function to extract dialogue from MP4 video
    """
    print(f"Processing video: {video_path}")
    
    # Check if video file exists
    if not os.path.exists(video_path):
        print("Error: Video file not found!")
        return
    
    try:
        # Step 1: Extract audio from video
        print("Extracting audio...")
        video = VideoFileClip(video_path)
        audio_path = "temp_audio.wav"
        video.audio.write_audiofile(audio_path, verbose=False, logger=None)
        video.close()
        print("Audio extracted successfully!")
        
        # Step 2: Convert audio to text
        print("Converting speech to text...")
        recognizer = sr.Recognizer()
        
        with sr.AudioFile(audio_path) as source:
            # Record the audio file
            audio_data = recognizer.record(source)
            
            # Convert to text
            text = recognizer.recognize_google(audio_data)
            print("\n--- EXTRACTED DIALOGUE ---")
            print(text)
            
            # Save to file
            with open("dialogue.txt", "w", encoding="utf-8") as f:
                f.write(text)
            print("\nDialogue saved to 'dialogue.txt'")
    
    except sr.UnknownValueError:
        print("Could not understand the audio")
    except sr.RequestError as e:
        print(f"Error with speech recognition service: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        # Clean up temporary audio file
        if os.path.exists("temp_audio.wav"):
            os.remove("temp_audio.wav")

# TO USE THIS SCRIPT:
# 1. Replace "your_video.mp4" with the path to your actual video file
# 2. Run the script

if __name__ == "__main__":
    # CHANGE THIS LINE - Put your video file path here:
    video_file = input("Enter the path to your MP4 video file: ").strip().strip('"')
    
    extract_dialogue(video_file)