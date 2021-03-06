import numpy as np
import tensorflow as tf
from tensorflow.keras.models import *
from tensorflow.keras.layers import Input, Conv2D, MaxPooling2D, UpSampling2D, Dropout, Cropping2D, Add, \
    Conv2DTranspose, BatchNormalization, InputLayer, Lambda
from tensorflow.python.keras import Input as InputUNET
from tensorflow.keras.optimizers import *
from tensorflow.keras import backend as keras
from tensorflow.keras.losses import sparse_categorical_crossentropy, categorical_crossentropy
from tensorflow.python.keras.callbacks import ModelCheckpoint, LearningRateScheduler


#LOSS FUNCTIONS
def categorical_focal_loss_fixed(y_true, y_pred):
    """
    :param y_true: A tensor of the same shape as `y_pred`
    :param y_pred: A tensor resulting from a softmax
    :return: Output tensor.
    """
    gamma=2.
    alpha=.25
    # Scale predictions so that the class probas of each sample sum to 1
    y_pred /= keras.sum(y_pred, axis=-1, keepdims=True)

    # Clip the prediction value to prevent NaN's and Inf's
    epsilon = keras.epsilon()
    y_pred = keras.clip(y_pred, epsilon, 1. - epsilon)

    # Calculate Cross Entropy
    cross_entropy = -y_true * keras.log(y_pred)

    # Calculate Focal Loss
    loss = alpha * keras.pow(1 - y_pred, gamma) * cross_entropy

    # Compute mean loss in mini_batch
    return keras.mean(loss, axis=1)
# import keras.losses
# keras.losses.custom_loss = custom_loss

# def my_categorical_crossentropy(output, target, from_logits=False):
#     """Categorical crossentropy between an output tensor and a target tensor.
#     # Arguments
#             output: A tensor resulting from a softmax
#                     (unless `from_logits` is True, in which
#                     case `output` is expected to be the logits).
#             target: A tensor of the same shape as `output`.
#             from_logits: Boolean, whether `output` is the
#                     result of a softmax, or is a tensor of logits.
#     # Returns
#             Output tensor.
#     """
#     # Note: tf.nn.softmax_cross_entropy_with_logits
#     # expects logits, Keras expects probabilities.
#     if not from_logits:
#         # scale preds so that the class probas of each sample sum to 1
#         output /= tf.reduce_sum(output, reduction_indices=len(output.get_shape()) - 1, keep_dims=True)
#         # manual computation of crossentropy
#         epsilon = _to_tensor(_EPSILON, output.dtype.base_dtype)
#         output = tf.clip_by_value(output, epsilon, 1. - epsilon)
#         return - tf.reduce_sum(target * tf.log(output), reduction_indices=len(output.get_shape()) - 1)
#     else:
#         return tf.nn.softmax_cross_entropy_with_logits(labels=target, logits=output)

def total_variation_loss(x):
    assert K.ndim(x) == 4
    # pdb.set_trace()
    img_nrows, img_ncols = x.shape[1:3]

    if K.image_data_format() == 'channels_first':
        a = K.square(
            x[:, :, :img_nrows - 1, :img_ncols - 1] - x[:, :, 1:, :img_ncols - 1])
        b = K.square(
            x[:, :, :img_nrows - 1, :img_ncols - 1] - x[:, :, :img_nrows - 1, 1:])
    else:
        a = K.square(
            x[:, :img_nrows - 1, :img_ncols - 1, :] - x[:, 1:, :img_ncols - 1, :])
        b = K.square(
            x[:, :img_nrows - 1, :img_ncols - 1, :] - x[:, :img_nrows - 1, 1:, :])
    return K.sum(K.pow(a + b, 1.25))

def custom_loss (y_true, y_pred):
    return categorical_crossentropy(y_true, y_pred) + 0.0001 * total_variation_loss(y_pred)
    # return 0.0001 * self.total_variation_loss(y_pred)

def categorical_focal_loss_fixed(self, y_true, y_pred):
    """
    :param y_true: A tensor of the same shape as `y_pred`
    :param y_pred: A tensor resulting from a softmax
    :return: Output tensor.
    """
    gamma=2.
    alpha=.25
    # Scale predictions so that the class probas of each sample sum to 1
    y_pred /= keras.sum(y_pred, axis=-1, keepdims=True)
    # Clip the prediction value to prevent NaN's and Inf's
    epsilon = keras.epsilon()
    y_pred = keras.clip(y_pred, epsilon, 1. - epsilon)
    # Calculate Cross Entropy
    cross_entropy = -y_true * keras.log(y_pred)
    # Calculate Focal Loss
    loss = alpha * keras.pow(1 - y_pred, gamma) * cross_entropy
    # Compute mean loss in mini_batch
    return keras.mean(loss, axis=1)

def dice_coef(self, y_true, y_pred):
    y_true_f = keras.flatten(y_true)
    y_pred_f = keras.flatten(y_pred)
    intersection = keras.sum(y_true_f * y_pred_f)
    #smooth here is to avoid divison by zero!
    return (2. * intersection + self.smooth) / (keras.sum(y_true_f) + keras.sum(y_pred_f) + self.smooth)
    # return (2. * intersection) / (K.sum(y_true_f) + K.sum(y_pred_f))

def dice_coef_multilabel(self, y_true, y_pred, numLabels=3):
    # return -dice_coef(y_true, y_pred)
    dice=0
    for index in range(numLabels):
            dice -= self.dice_coef(y_true[:,:,:,index], y_pred[:,:,:,index])
    return dice

def jaccard_coef_logloss(self, y_true, y_pred, smooth=1e-10):
    """ Loss function based on jaccard coefficient.
    Parameters
    ----------
    y_true : keras tensor
            tensor containing target mask.
    y_pred : keras tensor
            tensor containing predicted mask.
    smooth : float
            small real value used for avoiding division by zero error.
    Returns
    -------
    keras tensor
            tensor containing negative logarithm of jaccard coefficient.
    """
    y_true = keras.flatten(y_true)
    y_pred = keras.flatten(y_pred)
    truepos = keras.sum(y_true * y_pred)
    falsepos = keras.sum(y_pred) - truepos
    falseneg = keras.sum(y_true) - truepos
    jaccard = (truepos + smooth) / (smooth + truepos + falseneg + falsepos)
    return -keras.log(jaccard + smooth)

# UNET ARCHITECTURES
def unet_og_div_2(IMG_HEIGHT, IMG_WIDTH, IMG_CHANNELS, No_Classes, LearnRate):
    #og means it is architecture which is pretty much similar to the original architecture
    #div 2 means number of feature maps per conv layer were divided by 2 - computational reasons
    inputs = Input((IMG_HEIGHT, IMG_WIDTH, IMG_CHANNELS))
    c1 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (inputs)
    # c1 = Dropout(0.1) (c1)
    c1 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (c1)
    p1 = MaxPooling2D((2, 2)) (c1)

    c2 = Conv2D(64, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p1)
    # c2 = Dropout(0.1) (c2)
    c2 = Conv2D(64, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (c2)
    p2 = MaxPooling2D((2, 2)) (c2)

    c3 = Conv2D(128, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p2)
    # c3 = Dropout(0.1) (c3)
    c3 = Conv2D(128, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (c3)
    p3 = MaxPooling2D((2, 2)) (c3)

    c4 = Conv2D(256, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p3)
    # c4 = Dropout(0.1) (c4)
    c4 = Conv2D(256, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (c4)
    c4 = Dropout(0.5) (c4)
    p4 = MaxPooling2D(pool_size=(2, 2)) (c4)

    c5 = Conv2D(512, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p4)
    # c5 = Dropout(0.1) (c5)
    c5 = Conv2D(512, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (c5)
    c5 = Dropout(0.5) (c5)

    u6 = Conv2DTranspose(256, (2, 2), strides=(2, 2), padding='same') (c5)
    u6 = Add()([u6, c4])
    c6 = Conv2D(256, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u6)
    # c6 = Dropout(0.1) (c6)
    c6 = Conv2D(256, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (c6)

    u7 = Conv2DTranspose(128, (2, 2), strides=(2, 2), padding='same') (c6)
    u7 = Add()([u7, c3])
    c7 = Conv2D(128, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u7)
    # c7 = Dropout(0.1) (c7)
    c7 = Conv2D(128, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (c7)

    u8 = Conv2DTranspose(64, (2, 2), strides=(2, 2), padding='same') (c7)
    u8 = Add()([u8, c2])
    c8 = Conv2D(64, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u8)
    # c8 = Dropout(0.1) (c8)
    c8 = Conv2D(64, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (c8)

    u9 = Conv2DTranspose(32, (2, 2), strides=(2, 2), padding='same') (c8)
    u9 = Add()([u9, c1])
    c9 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u9)
    # c9 = Dropout(0.1) (c9)
    c9 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (c9)

    outputs = Conv2D(No_Classes, (1, 1), activation='softmax') (c9)

    model = Model(inputs=[inputs], outputs=[outputs])
    model.compile(optimizer = Adam(lr=LearnRate), loss= 'categorical_crossentropy' , metrics=['acc'])
    # model.compile(
    #        optimizer= Adadelta(),
    #        loss='sparse_categorical_crossentropy',
    #        metrics=['sparse_categorical_accuracy'])
    # model.summary()
    return model

def my_unet_batch_norm(IMG_HEIGHT, IMG_WIDTH, IMG_CHANNELS, No_Classes, LearnRate):
    #in this unet batch norm is included
    # inputs = InputUNET(shape=None)
    inputs = Input((IMG_HEIGHT, IMG_WIDTH, IMG_CHANNELS))
    s = Lambda(lambda x: x / 255) (inputs)
    # ipdb.set_trace()
    c1 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (s)
    b1 = BatchNormalization() (c1)
    # c1 = Conv2D(16, (3, 3), activation='relu', kernel_initializer='glorot_uniform', padding='same') (c1)
    p1 = MaxPooling2D((2, 2)) (b1)

    c2 = Conv2D(64, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p1)
    b2 = BatchNormalization() (c2)
    # c2 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='glorot_uniform', padding='same') (c2)
    p2 = MaxPooling2D((2, 2)) (b2)

    c3 = Conv2D(128, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p2)
    b3 = BatchNormalization() (c3)
    # c3 = Conv2D(64, (3, 3), activation='relu', kernel_initializer='glorot_uniform', padding='same') (c3)
    p3 = MaxPooling2D((2, 2)) (b3)

    c4 = Conv2D(256, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p3)
    b4 = BatchNormalization() (c4)
    # c4 = Conv2D(128, (3, 3), activation='relu', kernel_initializer='glorot_uniform', padding='same') (c4)
    p4 = MaxPooling2D((2, 2)) (b4)

    c5 = Conv2D(512, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p4)
    b5 = BatchNormalization() (c5)
    p5 = MaxPooling2D(pool_size=(2, 2)) (b5)

    c6 = Conv2D(1024, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p5)
    drop6 = Dropout(0.5) (c6)
    # c6 = Conv2D(512, (3, 3), activation='relu', kernel_initializer='glorot_uniform', padding='same') (drop6)

    u66 = Conv2DTranspose(512, (2, 2), strides=(2, 2), padding='same') (drop6)
    u66 = Add()([u66, c5])
    c66 = Conv2D(512, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u66)
    # c66 = Dropout(0.1) (c66)
    # c66 = Conv2D(256, (3, 3), activation='relu', kernel_initializer='glorot_uniform', padding='same') (c66)

    u6 = Conv2DTranspose(256, (2, 2), strides=(2, 2), padding='same') (c66)
    u6 = Add()([u6, c4])
    c6 = Conv2D(256, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u6)
    # c6 = Dropout(0.1) (c6)
    # c6 = Conv2D(128, (3, 3), activation='relu', kernel_initializer='glorot_uniform', padding='same') (c6)

    u7 = Conv2DTranspose(128, (2, 2), strides=(2, 2), padding='same') (c6)
    u7 = Add()([u7, c3])
    c7 = Conv2D(128, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u7)
    # c7 = Dropout(0.1) (c7)
    # c7 = Conv2D(64, (3, 3), activation='relu', kernel_initializer='glorot_uniform', padding='same') (c7)

    u8 = Conv2DTranspose(64, (2, 2), strides=(2, 2), padding='same') (c7)
    u8 = Add()([u8, c2])
    c8 = Conv2D(64, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u8)
    # c8 = Dropout(0.1) (c8)
    # c8 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='glorot_uniform', padding='same') (c8)

    u9 = Conv2DTranspose(32, (2, 2), strides=(2, 2), padding='same') (c8)
    u9 = Add()([u9, c1])
    c9 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u9)
    # c9 = Dropout(0.1) (c9)
    # c9 = Conv2D(16, (3, 3), activation='relu', kernel_initializer='glorot_uniform', padding='same') (c9)

    outputs = Conv2D(No_Classes, (1, 1), activation='softmax') (c9)

    model = Model(inputs=[inputs], outputs=[outputs])
    model.compile(optimizer = Adam(lr=LearnRate), loss= 'categorical_crossentropy' , metrics=['acc'])

    return model

def mini_unet_batch_norm(IMG_HEIGHT, IMG_WIDTH, IMG_CHANNELS, No_Classes, LearnRate):
    #in this unet batch norm is included
    # inputs = InputUNET(shape=None)
    inputs = Input((IMG_HEIGHT, IMG_WIDTH, IMG_CHANNELS))
    s = Lambda(lambda x: x / 255) (inputs)
    # ipdb.set_trace()
    c1 = Conv2D(8, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (s)
    b1 = BatchNormalization() (c1)
    # c1 = Conv2D(16, (3, 3), activation='relu', kernel_initializer='glorot_uniform', padding='same') (c1)
    p1 = MaxPooling2D((2, 2)) (b1)

    c2 = Conv2D(16, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p1)
    b2 = BatchNormalization() (c2)
    # c2 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='glorot_uniform', padding='same') (c2)
    p2 = MaxPooling2D((2, 2)) (b2)

    c3 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p2)
    b3 = BatchNormalization() (c3)
    # c3 = Conv2D(64, (3, 3), activation='relu', kernel_initializer='glorot_uniform', padding='same') (c3)
    p3 = MaxPooling2D((2, 2)) (b3)

    c4 = Conv2D(64, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p3)
    b4 = BatchNormalization() (c4)
    # c4 = Conv2D(128, (3, 3), activation='relu', kernel_initializer='glorot_uniform', padding='same') (c4)
    p4 = MaxPooling2D((2, 2)) (b4)

    c5 = Conv2D(128, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p4)
    b5 = BatchNormalization() (c5)
    p5 = MaxPooling2D(pool_size=(2, 2)) (b5)

    c6 = Conv2D(256, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p5)
    drop6 = Dropout(0.5) (c6)
    # c6 = Conv2D(512, (3, 3), activation='relu', kernel_initializer='glorot_uniform', padding='same') (drop6)

    u66 = Conv2DTranspose(128, (2, 2), strides=(2, 2), padding='same') (drop6)
    u66 = Add()([u66, c5])
    c66 = Conv2D(128, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u66)
    # c66 = Dropout(0.1) (c66)
    # c66 = Conv2D(256, (3, 3), activation='relu', kernel_initializer='glorot_uniform', padding='same') (c66)

    u6 = Conv2DTranspose(64, (2, 2), strides=(2, 2), padding='same') (c66)
    u6 = Add()([u6, c4])
    c6 = Conv2D(64, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u6)
    # c6 = Dropout(0.1) (c6)
    # c6 = Conv2D(128, (3, 3), activation='relu', kernel_initializer='glorot_uniform', padding='same') (c6)

    u7 = Conv2DTranspose(32, (2, 2), strides=(2, 2), padding='same') (c6)
    u7 = Add()([u7, c3])
    c7 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u7)
    # c7 = Dropout(0.1) (c7)
    # c7 = Conv2D(64, (3, 3), activation='relu', kernel_initializer='glorot_uniform', padding='same') (c7)

    u8 = Conv2DTranspose(16, (2, 2), strides=(2, 2), padding='same') (c7)
    u8 = Add()([u8, c2])
    c8 = Conv2D(16, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u8)
    # c8 = Dropout(0.1) (c8)
    # c8 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='glorot_uniform', padding='same') (c8)

    u9 = Conv2DTranspose(8, (2, 2), strides=(2, 2), padding='same') (c8)
    u9 = Add()([u9, c1])
    c9 = Conv2D(8, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u9)
    # c9 = Dropout(0.1) (c9)
    # c9 = Conv2D(16, (3, 3), activation='relu', kernel_initializer='glorot_uniform', padding='same') (c9)

    outputs = Conv2D(No_Classes, (1, 1), activation='sigmoid') (c9)

    model = Model(inputs=[inputs], outputs=[outputs])
    model.compile(optimizer = Adam(lr=LearnRate), loss= 'categorical_crossentropy' , metrics=['acc'])

    return model

def narrow_deep_unet(IMG_HEIGHT, IMG_WIDTH, IMG_CHANNELS, No_Classes, LearnRate):
    #in this unet batch norm is included
    # inputs = InputUNET(shape=None)
    inputs = Input((IMG_HEIGHT, IMG_WIDTH, IMG_CHANNELS))
    # s = Lambda(lambda x: x / 255) (inputs)
    # ipdb.set_trace()
    c1 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (inputs)
    b1 = BatchNormalization() (c1)
    # c1 = Conv2D(16, (3, 3), activation='relu', kernel_initializer='glorot_uniform', padding='same') (c1)
    p1 = MaxPooling2D((2, 2)) (b1)

    c2 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p1)
    b2 = BatchNormalization() (c2)
    # c2 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='glorot_uniform', padding='same') (c2)
    p2 = MaxPooling2D((2, 2)) (b2)

    c3 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p2)
    b3 = BatchNormalization() (c3)
    # c3 = Conv2D(64, (3, 3), activation='relu', kernel_initializer='glorot_uniform', padding='same') (c3)
    p3 = MaxPooling2D((2, 2)) (b3)

    c4 = Conv2D(64, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p3)
    b4 = BatchNormalization() (c4)
    # c4 = Conv2D(128, (3, 3), activation='relu', kernel_initializer='glorot_uniform', padding='same') (c4)
    p4 = MaxPooling2D((2, 2)) (b4)

    c5 = Conv2D(64, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p4)
    b5 = BatchNormalization() (c5)
    p5 = MaxPooling2D(pool_size=(2, 2)) (b5)

    c6 = Conv2D(64, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p5)
    b6 = BatchNormalization() (c6)
    p6 = MaxPooling2D(pool_size=(2, 2)) (b6)

    c7 = Conv2D(64, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p6)
    b7 = BatchNormalization() (c7)
    p7 = MaxPooling2D(pool_size=(2, 2)) (b7)

    c8 = Conv2D(128, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p7)
    b8 = BatchNormalization() (c8)
    p8 = MaxPooling2D(pool_size=(2, 2)) (b8)

    c9 = Conv2D(256, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p8)
    b9 = BatchNormalization() (c9)
    p9 = MaxPooling2D(pool_size=(2, 2)) (b9)

    c99 = Conv2D(256, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p9)
    b99 = BatchNormalization() (c99)
    p99 = MaxPooling2D(pool_size=(2, 2)) (b99)

    c10 = Conv2D(512, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p99)
    drop10 = Dropout(0.5) (c10)

    u111 = Conv2DTranspose(256, (2, 2), strides=(2, 2), padding='same') (drop10)
    u111 = Add()([u111, c99])
    c111 = Conv2D(256, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u111)

    u11 = Conv2DTranspose(256, (2, 2), strides=(2, 2), padding='same') (c111)
    u11 = Add()([u11, c9])
    c11 = Conv2D(256, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u11)

    u12 = Conv2DTranspose(128, (2, 2), strides=(2, 2), padding='same') (c11)
    u12 = Add()([u12, c8])
    c12 = Conv2D(128, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u12)

    u13 = Conv2DTranspose(64, (2, 2), strides=(2, 2), padding='same') (c12)
    u13 = Add()([u13, c7])
    c13 = Conv2D(64, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u13)

    u14 = Conv2DTranspose(64, (2, 2), strides=(2, 2), padding='same') (c13)
    u14 = Add()([u14, c6])
    c14 = Conv2D(64, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u14)

    u15 = Conv2DTranspose(64, (2, 2), strides=(2, 2), padding='same') (c14)
    u15 = Add()([u15, c5])
    c15 = Conv2D(64, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u15)

    u16 = Conv2DTranspose(64, (2, 2), strides=(2, 2), padding='same') (c15)
    u16 = Add()([u16, c4])
    c16 = Conv2D(64, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u16)

    u17 = Conv2DTranspose(32, (2, 2), strides=(2, 2), padding='same') (c16)
    u17 = Add()([u17, c3])
    c17 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u17)

    u18 = Conv2DTranspose(32, (2, 2), strides=(2, 2), padding='same') (c17)
    u18 = Add()([u18, c2])
    c18 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u18)

    u19 = Conv2DTranspose(32, (2, 2), strides=(2, 2), padding='same') (c18)
    u19 = Add()([u19, c1])
    c19 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u19)

    outputs = Conv2D(No_Classes, (1, 1), activation='softmax') (c19)

    model = Model(inputs=[inputs], outputs=[outputs])
    model.compile(optimizer = Adam(lr=LearnRate), loss= 'categorical_crossentropy' , metrics=['acc'])

    return model

def narrow_deep_Anet(IMG_HEIGHT, IMG_WIDTH, IMG_CHANNELS, No_Classes, LearnRate):
    #in this unet batch norm is included
    # inputs = InputUNET(shape=None)
    inputs = Input((IMG_HEIGHT, IMG_WIDTH, IMG_CHANNELS))
    s = Lambda(lambda x: x / 255) (inputs)
    # ipdb.set_trace()
    c1 = Conv2D(64, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (s)
    b1 = BatchNormalization() (c1)
    # c1 = Conv2D(16, (3, 3), activation='relu', kernel_initializer='glorot_uniform', padding='same') (c1)
    p1 = MaxPooling2D((2, 2)) (b1)

    c2 = Conv2D(64, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p1)
    b2 = BatchNormalization() (c2)
    # c2 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='glorot_uniform', padding='same') (c2)
    p2 = MaxPooling2D((2, 2)) (b2)

    c3 = Conv2D(64, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p2)
    b3 = BatchNormalization() (c3)
    # c3 = Conv2D(64, (3, 3), activation='relu', kernel_initializer='glorot_uniform', padding='same') (c3)
    p3 = MaxPooling2D((2, 2)) (b3)

    c4 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p3)
    b4 = BatchNormalization() (c4)
    # c4 = Conv2D(128, (3, 3), activation='relu', kernel_initializer='glorot_uniform', padding='same') (c4)
    p4 = MaxPooling2D((2, 2)) (b4)

    c5 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p4)
    b5 = BatchNormalization() (c5)
    p5 = MaxPooling2D(pool_size=(2, 2)) (b5)

    c6 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p5)
    b6 = BatchNormalization() (c6)
    p6 = MaxPooling2D(pool_size=(2, 2)) (b6)

    c7 = Conv2D(16, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p6)
    b7 = BatchNormalization() (c7)
    p7 = MaxPooling2D(pool_size=(2, 2)) (b7)

    c8 = Conv2D(16, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p7)
    b8 = BatchNormalization() (c8)
    p8 = MaxPooling2D(pool_size=(2, 2)) (b8)
    #this 9th block is taken out for images of size 256 because it will convolute it to size 0
    # c9 = Conv2D(16, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p8)
    # b9 = BatchNormalization() (c9)
    # p9 = MaxPooling2D(pool_size=(2, 2)) (b9)

    c10 = Conv2D(8, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p8)
    drop10 = Dropout(0.5) (c10)

    # u11 = Conv2DTranspose(16, (2, 2), strides=(2, 2), padding='same') (drop10)
    # u11 = Add()([u11, c9])
    # c11 = Conv2D(16, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u11)

    u12 = Conv2DTranspose(16, (2, 2), strides=(2, 2), padding='same') (drop10)
    u12 = Add()([u12, c8])
    c12 = Conv2D(16, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u12)

    u13 = Conv2DTranspose(16, (2, 2), strides=(2, 2), padding='same') (c12)
    u13 = Add()([u13, c7])
    c13 = Conv2D(16, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u13)

    u14 = Conv2DTranspose(32, (2, 2), strides=(2, 2), padding='same') (c13)
    u14 = Add()([u14, c6])
    c14 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u14)

    u15 = Conv2DTranspose(32, (2, 2), strides=(2, 2), padding='same') (c14)
    u15 = Add()([u15, c5])
    c15 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u15)

    u16 = Conv2DTranspose(32, (2, 2), strides=(2, 2), padding='same') (c15)
    u16 = Add()([u16, c4])
    c16 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u16)

    u17 = Conv2DTranspose(64, (2, 2), strides=(2, 2), padding='same') (c16)
    u17 = Add()([u17, c3])
    c17 = Conv2D(64, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u17)

    u18 = Conv2DTranspose(64, (2, 2), strides=(2, 2), padding='same') (c17)
    u18 = Add()([u18, c2])
    c18 = Conv2D(64, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u18)

    u19 = Conv2DTranspose(64, (2, 2), strides=(2, 2), padding='same') (c18)
    u19 = Add()([u19, c1])
    c19 = Conv2D(64, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u19)

    outputs = Conv2D(No_Classes, (1, 1), activation='softmax') (c19)
    if No_Classes > 2:
        loss = 'categorical_crossentropy'
    else:
        loss = 'binary_crossentropy'

    model = Model(inputs=[inputs], outputs=[outputs])
    model.compile(optimizer = Adam(lr=LearnRate), loss= loss , metrics=['acc'])

    return model

def narrow_deep_Mnet(IMG_HEIGHT, IMG_WIDTH, IMG_CHANNELS, No_Classes, LearnRate):
    #in this unet batch norm is included
    # inputs = InputUNET(shape=None)
    inputs = Input((IMG_HEIGHT, IMG_WIDTH, IMG_CHANNELS))
    # s = Lambda(lambda x: x / 255) (inputs)
    # ipdb.set_trace()
    c1 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (inputs)
    b1 = BatchNormalization() (c1)
    # c1 = Conv2D(16, (3, 3), activation='relu', kernel_initializer='glorot_uniform', padding='same') (c1)
    p1 = MaxPooling2D((2, 2)) (b1)

    c2 = Conv2D(64, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p1)
    b2 = BatchNormalization() (c2)
    # c2 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='glorot_uniform', padding='same') (c2)
    p2 = MaxPooling2D((2, 2)) (b2)

    c3 = Conv2D(128, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p2)
    b3 = BatchNormalization() (c3)
    # c3 = Conv2D(64, (3, 3), activation='relu', kernel_initializer='glorot_uniform', padding='same') (c3)
    p3 = MaxPooling2D((2, 2)) (b3)

    c4 = Conv2D(64, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p3)
    b4 = BatchNormalization() (c4)
    # c4 = Conv2D(128, (3, 3), activation='relu', kernel_initializer='glorot_uniform', padding='same') (c4)
    p4 = MaxPooling2D((2, 2)) (b4)

    c5 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p4)
    b5 = BatchNormalization() (c5)
    p5 = MaxPooling2D(pool_size=(2, 2)) (b5)

    c6 = Conv2D(16, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p5)
    b6 = BatchNormalization() (c6)
    p6 = MaxPooling2D(pool_size=(2, 2)) (b6)

    c7 = Conv2D(8, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p6)
    b7 = BatchNormalization() (c7)
    p7 = MaxPooling2D(pool_size=(2, 2)) (b7)

    c8 = Conv2D(16, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p7)
    b8 = BatchNormalization() (c8)
    p8 = MaxPooling2D(pool_size=(2, 2)) (b8)

    c9 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p8)
    b9 = BatchNormalization() (c9)
    p9 = MaxPooling2D(pool_size=(2, 2)) (b9)

    c10 = Conv2D(64, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p9)
    drop10 = Dropout(0.5) (c10)

    u11 = Conv2DTranspose(32, (2, 2), strides=(2, 2), padding='same') (drop10)
    u11 = Add()([u11, c9])
    c11 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u11)

    u12 = Conv2DTranspose(16, (2, 2), strides=(2, 2), padding='same') (c11)
    u12 = Add()([u12, c8])
    c12 = Conv2D(16, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u12)

    u13 = Conv2DTranspose(8, (2, 2), strides=(2, 2), padding='same') (c12)
    u13 = Add()([u13, c7])
    c13 = Conv2D(8, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u13)

    u14 = Conv2DTranspose(16, (2, 2), strides=(2, 2), padding='same') (c13)
    u14 = Add()([u14, c6])
    c14 = Conv2D(16, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u14)

    u15 = Conv2DTranspose(32, (2, 2), strides=(2, 2), padding='same') (c14)
    u15 = Add()([u15, c5])
    c15 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u15)

    u16 = Conv2DTranspose(64, (2, 2), strides=(2, 2), padding='same') (c15)
    u16 = Add()([u16, c4])
    c16 = Conv2D(64, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u16)

    u17 = Conv2DTranspose(128, (2, 2), strides=(2, 2), padding='same') (c16)
    u17 = Add()([u17, c3])
    c17 = Conv2D(128, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u17)

    u18 = Conv2DTranspose(64, (2, 2), strides=(2, 2), padding='same') (c17)
    u18 = Add()([u18, c2])
    c18 = Conv2D(64, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u18)

    u19 = Conv2DTranspose(32, (2, 2), strides=(2, 2), padding='same') (c18)
    u19 = Add()([u19, c1])
    c19 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u19)

    outputs = Conv2D(No_Classes, (1, 1), activation='softmax') (c19)

    model = Model(inputs=[inputs], outputs=[outputs])
    model.compile(optimizer = Adam(lr=LearnRate), loss= 'categorical_crossentropy' , metrics=['acc'])

    return model

def filter_Net(IMG_HEIGHT, IMG_WIDTH, IMG_CHANNELS, No_Classes, LearnRate):
    #in this unet batch norm is included
    # inputs = InputUNET(shape=None)
    inputs = Input((IMG_HEIGHT, IMG_WIDTH, IMG_CHANNELS))
    # s = Lambda(lambda x: x / 255) (inputs)
    # ipdb.set_trace()
    c1 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (inputs)
    b1 = BatchNormalization() (c1)
    # c1 = Conv2D(16, (3, 3), activation='relu', kernel_initializer='glorot_uniform', padding='same') (c1)
    p1 = MaxPooling2D((2, 2)) (b1)

    c2 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p1)
    b2 = BatchNormalization() (c2)
    # c2 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='glorot_uniform', padding='same') (c2)
    p2 = MaxPooling2D((2, 2)) (b2)

    c3 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p2)
    b3 = BatchNormalization() (c3)
    # c3 = Conv2D(64, (3, 3), activation='relu', kernel_initializer='glorot_uniform', padding='same') (c3)
    p3 = MaxPooling2D((2, 2)) (b3)

    c4 = Conv2D(32, (5, 5), activation='relu', kernel_initializer='he_normal', padding='same') (p3)
    b4 = BatchNormalization() (c4)
    # c4 = Conv2D(128, (3, 3), activation='relu', kernel_initializer='glorot_uniform', padding='same') (c4)
    p4 = MaxPooling2D((2, 2)) (b4)

    c5 = Conv2D(32, (5, 5), activation='relu', kernel_initializer='he_normal', padding='same') (p4)
    b5 = BatchNormalization() (c5)
    p5 = MaxPooling2D(pool_size=(2, 2)) (b5)

    c6 = Conv2D(32, (5, 5), activation='relu', kernel_initializer='he_normal', padding='same') (p5)
    b6 = BatchNormalization() (c6)
    p6 = MaxPooling2D(pool_size=(2, 2)) (b6)

    c7 = Conv2D(32, (5, 5), activation='relu', kernel_initializer='he_normal', padding='same') (p6)
    b7 = BatchNormalization() (c7)
    p7 = MaxPooling2D(pool_size=(2, 2)) (b7)

    c8 = Conv2D(32, (5, 5), activation='relu', kernel_initializer='he_normal', padding='same') (p7)
    b8 = BatchNormalization() (c8)
    p8 = MaxPooling2D(pool_size=(2, 2)) (b8)

    c9 = Conv2D(32, (5, 5), activation='relu', kernel_initializer='he_normal', padding='same') (p8)
    b9 = BatchNormalization() (c9)
    p9 = MaxPooling2D(pool_size=(2, 2)) (b9)

    c10 = Conv2D(32, (5, 5), activation='relu', kernel_initializer='he_normal', padding='same') (p9)
    drop10 = Dropout(0.5) (c10)

    u11 = Conv2DTranspose(32, (2, 2), strides=(2, 2), padding='same') (drop10)
    u11 = Add()([u11, c9])
    c11 = Conv2D(32, (5, 5), activation='relu', kernel_initializer='he_normal', padding='same') (u11)

    u12 = Conv2DTranspose(32, (2, 2), strides=(2, 2), padding='same') (c11)
    u12 = Add()([u12, c8])
    c12 = Conv2D(32, (5, 5), activation='relu', kernel_initializer='he_normal', padding='same') (u12)

    u13 = Conv2DTranspose(32, (2, 2), strides=(2, 2), padding='same') (c12)
    u13 = Add()([u13, c7])
    c13 = Conv2D(32, (5, 5), activation='relu', kernel_initializer='he_normal', padding='same') (u13)

    u14 = Conv2DTranspose(32, (2, 2), strides=(2, 2), padding='same') (c13)
    u14 = Add()([u14, c6])
    c14 = Conv2D(32, (5, 5), activation='relu', kernel_initializer='he_normal', padding='same') (u14)

    u15 = Conv2DTranspose(32, (2, 2), strides=(2, 2), padding='same') (c14)
    u15 = Add()([u15, c5])
    c15 = Conv2D(32, (5, 5), activation='relu', kernel_initializer='he_normal', padding='same') (u15)

    u16 = Conv2DTranspose(32, (2, 2), strides=(2, 2), padding='same') (c15)
    u16 = Add()([u16, c4])
    c16 = Conv2D(32, (5, 5), activation='relu', kernel_initializer='he_normal', padding='same') (u16)

    u17 = Conv2DTranspose(32, (2, 2), strides=(2, 2), padding='same') (c16)
    u17 = Add()([u17, c3])
    c17 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u17)

    u18 = Conv2DTranspose(32, (2, 2), strides=(2, 2), padding='same') (c17)
    u18 = Add()([u18, c2])
    c18 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u18)

    u19 = Conv2DTranspose(32, (2, 2), strides=(2, 2), padding='same') (c18)
    u19 = Add()([u19, c1])
    c19 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u19)

    outputs = Conv2D(No_Classes, (1, 1), activation='softmax') (c19)

    model = Model(inputs=[inputs], outputs=[outputs])
    if No_Classes > 2:
        loss = 'binary_crossentropy'
    else:
        loss = 'categorical_crossentropy'
    model.compile(optimizer = Adam(lr=LearnRate), loss= loss , metrics=['acc'])

    return model

def narrower_deeper_Anet(IMG_HEIGHT, IMG_WIDTH, IMG_CHANNELS, No_Classes, LearnRate):
    #in this unet batch norm is included
    # inputs = InputUNET(shape=None)
    inputs = Input((IMG_HEIGHT, IMG_WIDTH, IMG_CHANNELS))
    # s = Lambda(lambda x: x / 255) (inputs)
    # ipdb.set_trace()
    c1 = Conv2D(64, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (inputs)
    b1 = BatchNormalization() (c1)
    # c1 = Conv2D(16, (3, 3), activation='relu', kernel_initializer='glorot_uniform', padding='same') (c1)
    p1 = MaxPooling2D((2, 2)) (b1)

    c2 = Conv2D(64, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p1)
    b2 = BatchNormalization() (c2)
    # c2 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='glorot_uniform', padding='same') (c2)
    p2 = MaxPooling2D((2, 2)) (b2)

    c3 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p2)
    b3 = BatchNormalization() (c3)
    # c3 = Conv2D(64, (3, 3), activation='relu', kernel_initializer='glorot_uniform', padding='same') (c3)
    p3 = MaxPooling2D((2, 2)) (b3)

    c4 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p3)
    b4 = BatchNormalization() (c4)
    # c4 = Conv2D(128, (3, 3), activation='relu', kernel_initializer='glorot_uniform', padding='same') (c4)
    p4 = MaxPooling2D((2, 2)) (b4)

    c5 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p4)
    b5 = BatchNormalization() (c5)
    p5 = MaxPooling2D(pool_size=(2, 2)) (b5)

    c6 = Conv2D(16, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p5)
    b6 = BatchNormalization() (c6)
    p6 = MaxPooling2D(pool_size=(2, 2)) (b6)

    c7 = Conv2D(16, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p6)
    b7 = BatchNormalization() (c7)
    p7 = MaxPooling2D(pool_size=(2, 2)) (b7)

    c8 = Conv2D(16, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p7)
    b8 = BatchNormalization() (c8)
    p8 = MaxPooling2D(pool_size=(2, 2)) (b8)

    c9 = Conv2D(16, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p8)
    b9 = BatchNormalization() (c9)
    p9 = MaxPooling2D(pool_size=(2, 2)) (b9)

    c99 = Conv2D(8, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p9)
    b99 = BatchNormalization() (c99)
    p99 = MaxPooling2D(pool_size=(2, 2)) (b99)

    # c999 = Conv2D(8, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p99)
    # b999 = BatchNormalization() (c999)
    # p999 = MaxPooling2D(pool_size=(2, 2)) (b999)

    c10 = Conv2D(8, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (p99)
    drop10 = Dropout(0.5) (c10)

    # u1111 = Conv2DTranspose(8, (2, 2), strides=(2, 2), padding='same') (drop10)
    # u1111 = Add()([u1111, c999])
    # c1111 = Conv2D(8, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u1111)

    u111 = Conv2DTranspose(8, (2, 2), strides=(2, 2), padding='same') (drop10)
    u111 = Add()([u111, c99])
    c111 = Conv2D(8, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u111)

    u11 = Conv2DTranspose(16, (2, 2), strides=(2, 2), padding='same') (c111)
    u11 = Add()([u11, c9])
    c11 = Conv2D(16, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u11)

    u12 = Conv2DTranspose(16, (2, 2), strides=(2, 2), padding='same') (c11)
    u12 = Add()([u12, c8])
    c12 = Conv2D(16, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u12)

    u13 = Conv2DTranspose(16, (2, 2), strides=(2, 2), padding='same') (c12)
    u13 = Add()([u13, c7])
    c13 = Conv2D(16, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u13)

    u14 = Conv2DTranspose(16, (2, 2), strides=(2, 2), padding='same') (c13)
    u14 = Add()([u14, c6])
    c14 = Conv2D(16, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u14)

    u15 = Conv2DTranspose(32, (2, 2), strides=(2, 2), padding='same') (c14)
    u15 = Add()([u15, c5])
    c15 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u15)

    u16 = Conv2DTranspose(32, (2, 2), strides=(2, 2), padding='same') (c15)
    u16 = Add()([u16, c4])
    c16 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u16)

    u17 = Conv2DTranspose(32, (2, 2), strides=(2, 2), padding='same') (c16)
    u17 = Add()([u17, c3])
    c17 = Conv2D(32, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u17)

    u18 = Conv2DTranspose(64, (2, 2), strides=(2, 2), padding='same') (c17)
    u18 = Add()([u18, c2])
    c18 = Conv2D(64, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u18)

    u19 = Conv2DTranspose(64, (2, 2), strides=(2, 2), padding='same') (c18)
    u19 = Add()([u19, c1])
    c19 = Conv2D(64, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same') (u19)

    outputs = Conv2D(No_Classes, (1, 1), activation='softmax') (c19)

    model = Model(inputs=[inputs], outputs=[outputs])
    model.compile(optimizer = Adam(lr=LearnRate), loss= 'categorical_crossentropy' , metrics=['acc'])

    return model